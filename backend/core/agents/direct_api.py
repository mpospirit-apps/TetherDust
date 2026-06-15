"""Direct API agent (Option 3).

Runs the agentic tool-call loop in-process inside Django using `httpx`, calling
an OpenAI-compatible chat-completions endpoint directly. No Codex container, no
CLI subprocess. Every tool the model can reach is an MCP tool, so role-based
filtering applies uniformly.

`OpenAICompatibleAgent` targets `POST {base_url}/chat/completions` and works
against OpenAI, Azure OpenAI, OpenRouter, and local Ollama by changing only
`base_url`/`model`. Provider-specific request building and stream parsing are
factored into overridable methods so an Anthropic `/v1/messages` sibling can be
added later without touching the MCP/tool-loop plumbing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx as httpx

from .base import BaseAgent
from .history import HistoryMessages
from .mcp_filter import (
    clear_filter,
    register_filter,
    tokenized_mcp_url,
)
from .mcp_session import call_tool_text, mcp_tools_to_openai, open_mcp_session
from .stream import ERROR_PREFIX, RESPONSE_PREFIX, THINKING_PREFIX, TOOL_PREFIX

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models import AgentConfiguration

DIRECT_API_CONNECT_TIMEOUT = float(os.getenv("DIRECT_API_CONNECT_TIMEOUT", "30"))
DIRECT_API_RESPONSE_TIMEOUT = float(os.getenv("DIRECT_API_RESPONSE_TIMEOUT", "300"))
# Hard cap on tool-call rounds, so a model that keeps requesting tools can never
# loop forever.
MAX_TOOL_ROUNDS = int(os.getenv("DIRECT_API_MAX_TOOL_ROUNDS", "25"))

# OpenRouter's recommended attribution headers (used for its app rankings /
# dashboards). Both are optional; override via env to customize per deployment.
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "https://tetherdust.local")
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "TetherDust")


class ProviderAPIError(Exception):
    """The provider returned an HTTP >= 400 response.

    Carries the parsed, human-readable provider message (e.g. an invalid-model or
    auth error) so `chat()` can surface it to the session log rather than letting
    it collapse into the generic "unexpected error" path.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Provider returned HTTP {status_code}: {detail}")


def _extract_provider_error(raw: str | None) -> str:
    """Pull a readable message out of a provider's error body.

    OpenAI-compatible providers (OpenAI, Anthropic's compat endpoint, OpenRouter)
    return `{"error": {"message": ..., "code": ...}}`; fall back to the raw body
    when it isn't that shape.
    """
    raw = (raw or "").strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "").strip() or raw
    if isinstance(err, str):
        return err.strip() or raw
    return raw


def _root_cause(exc: BaseException) -> BaseException:
    """Drill through ExceptionGroups to the leaf cause.

    Errors raised inside the MCP `ClientSession` task group surface as nested
    `ExceptionGroup`s (anyio re-raises background-task failures grouped), so the
    real cause — e.g. a `ProviderAPIError` — is buried. Without unwrapping, every
    failure matches only the generic `except Exception` and loses its specifics.
    """
    seen: set[int] = set()
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and id(exc) not in seen:
        seen.add(id(exc))
        exc = exc.exceptions[0]
    return exc


class OpenAICompatibleAgent(BaseAgent):
    """Direct API agent for OpenAI-compatible `/chat/completions` endpoints."""

    # Whether a provider API key is mandatory. Cloud providers (OpenAI, Azure,
    # OpenRouter) require one; a self-hosted Ollama does not — subclasses can
    # flip this off.
    REQUIRES_API_KEY = True

    def __init__(self, config: AgentConfiguration | None = None) -> None:
        self._config = config
        self._system_prompt = config.system_prompt if config else ""
        self._api_key = config.get_api_key() if config else ""
        settings = (getattr(config, "settings", None) or {}) if config else {}
        if not isinstance(settings, dict):
            settings = {}
        self._model = (settings.get("model") or "").strip()
        self._base_url = (settings.get("base_url") or "").strip().rstrip("/")
        self._max_tokens = settings.get("max_tokens")
        self._http_response: httpx.Response | None = None

    # --- BaseAgent contract --------------------------------------------

    def supports_mcp(self) -> bool:
        return True

    def get_name(self) -> str:
        return "OpenAI-compatible API (Direct)"

    # --- Provider-specific request hooks (overridable) -----------------

    def _extra_headers(self) -> dict[str, str]:
        """Provider-specific HTTP headers merged into each request. Default: none."""
        return {}

    def _extra_body(self) -> dict[str, Any]:
        """Provider-specific request-body fields merged into each request. Default: none."""
        return {}

    async def cancel(self) -> None:
        """Close the active provider stream so a cancelled request stops promptly."""
        if self._http_response is not None:
            try:
                await self._http_response.aclose()
            except Exception:
                pass
            self._http_response = None

    def _classify_error(self, exc: BaseException) -> tuple[str, str]:
        """Map an error to a (user-facing message, session-log detail) pair.

        The first is the friendly chunk shown in chat; the second is the real
        cause persisted to the session log so an admin can diagnose it.
        """
        root = _root_cause(exc)
        if isinstance(root, ProviderAPIError):
            return (
                "\n\nThe AI provider rejected the request. Check the agent's "
                "model and base URL, then try again.",
                f"Provider HTTP {root.status_code}: {root.detail}",
            )
        if isinstance(root, TimeoutError):
            return (
                "\n\nThe response timed out. Your query may be too complex — try "
                "simplifying it or breaking it into smaller questions.",
                "Provider response timeout exceeded",
            )
        if isinstance(root, httpx.ConnectError):
            return (
                "\n\nUnable to reach the AI provider. Check the agent's base URL "
                "and that the service is reachable.",
                f"Cannot connect to provider API at {self._base_url}: {root}",
            )
        if isinstance(root, httpx.TimeoutException):
            return (
                "\n\nThe AI provider is not responding. Please try again in a moment.",
                f"Timeout talking to provider API at {self._base_url}: {root}",
            )
        if isinstance(root, httpx.ReadError):
            return (
                "\n\nThe connection to the AI provider was interrupted. Please try "
                "sending your message again.",
                f"Read error from provider API: {root}",
            )
        return (
            "\n\nAn unexpected error occurred while contacting the AI provider. "
            "Please try again or contact your administrator.",
            f"{type(root).__name__}: {root}",
        )

    # --- Main loop ------------------------------------------------------

    async def chat(
        self,
        message: str,
        user_id: int,
        session_id: str,
        allowed_tools: list[str] | None = None,
        allowed_databases: list[str] | None = None,
        allowed_doc_sources: list[str] | None = None,
        max_row_limit: int | None = None,
        timeout: float | None = None,
        custom_mcp_servers: list[dict[str, Any]] | None = None,
        history: HistoryMessages | None = None,
        allowed_codebases: list[str] | None = None,
        allowed_reports: list[str] | None = None,
        allowed_dashboards: list[str] | None = None,
        allowed_tethers: list[str] | None = None,
    ) -> AsyncIterator[str]:
        if not self._model or not self._base_url:
            yield (
                "\n\nThis agent is not fully configured. Set its model and base "
                "URL in the admin before using it."
            )
            return
        if self.REQUIRES_API_KEY and not self._api_key:
            yield (
                "\n\nThis agent has no API key configured. Add the provider API "
                "key in the admin before using it."
            )
            return
        if custom_mcp_servers:
            # v1 scope: built-in MCP server only.
            logger.warning(
                "OpenAICompatibleAgent ignoring %d custom MCP server(s) (not supported in v1).",
                len(custom_mcp_servers),
            )

        response_timeout = timeout or DIRECT_API_RESPONSE_TIMEOUT

        # Register the per-request MCP filter (agent-agnostic) and connect to the
        # tokenized URL. A token is ALWAYS registered — even for an unrestricted
        # request (all-None filters = all-access) — because the MCP server fails
        # closed and rejects any untokenized /mcp request.
        filter_token: str | None = None
        try:
            filter_token = await register_filter(
                allowed_tools=allowed_tools,
                allowed_databases=allowed_databases,
                allowed_doc_sources=allowed_doc_sources,
                allowed_codebases=allowed_codebases,
                allowed_reports=allowed_reports,
                allowed_dashboards=allowed_dashboards,
                allowed_tethers=allowed_tethers,
                max_row_limit=max_row_limit,
            )
        except httpx.ConnectError:
            logger.error("Cannot connect to MCP server for filter registration")
            yield (
                "\n\nUnable to reach the MCP server for security filter "
                "registration. The service may be starting up or temporarily "
                "unavailable."
            )
            return
        except httpx.TimeoutException:
            logger.error("Timeout registering filter with MCP server")
            yield "\n\nThe MCP server is not responding. Please try again in a moment."
            return
        except Exception:
            logger.exception("Unexpected error during MCP filter registration")
            yield (
                "\n\nAn unexpected error occurred while setting up security "
                "filters. Please try again."
            )
            return
        mcp_url = tokenized_mcp_url(filter_token)
        # Exposed so the consumer can fetch this turn's (token-scoped) tool calls.
        self._last_filter_token = filter_token

        try:
            async with asyncio.timeout(response_timeout):
                async for chunk in self._run_with_mcp(mcp_url, message, history):
                    yield chunk
        except Exception as exc:
            # Errors bubble up wrapped in ExceptionGroups (MCP task group), so
            # classify against the unwrapped root cause. Yield the friendly chunk
            # for the user AND an ERROR marker carrying the real cause, which the
            # consumer persists to the session log — parity with the CLI agents.
            friendly, detail = self._classify_error(exc)
            logger.error("Direct API agent error: %s", detail, exc_info=True)
            yield friendly
            yield f"{ERROR_PREFIX}{detail}"
        finally:
            self._http_response = None
            if filter_token:
                await clear_filter(filter_token)

    async def _run_with_mcp(
        self, mcp_url: str, message: str, history: HistoryMessages | None
    ) -> AsyncIterator[str]:
        """Open the MCP session and drive the provider tool-call loop."""
        async with open_mcp_session(mcp_url) as session:
            tools = mcp_tools_to_openai(await session.list_tools())

            messages: list[dict[str, Any]] = []
            if self._system_prompt.strip():
                messages.append({"role": "system", "content": self._system_prompt})
            for turn in history or []:
                role = "assistant" if turn.get("role") == "assistant" else "user"
                content = turn.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": message})

            http_timeout = httpx.Timeout(
                connect=DIRECT_API_CONNECT_TIMEOUT,
                read=None,
                write=30,
                pool=30,
            )
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                final_text = ""
                for _round in range(MAX_TOOL_ROUNDS):
                    final_text, tool_calls = "", {}
                    async for kind, text, calls in self._stream_round(client, messages, tools):
                        if kind == "text":
                            final_text += text
                            yield text
                        elif kind == "thinking":
                            yield f"{THINKING_PREFIX}{text}"
                        elif kind == "tool_calls":
                            tool_calls = calls

                    if not tool_calls:
                        yield f"{RESPONSE_PREFIX}{final_text}"
                        return

                    # Feed the tool calls + results back and loop.
                    ordered = [tool_calls[i] for i in sorted(tool_calls)]
                    messages.append(
                        {
                            "role": "assistant",
                            "content": final_text or None,
                            "tool_calls": [
                                {
                                    "id": c["id"] or f"call_{idx}",
                                    "type": "function",
                                    "function": {
                                        "name": c["name"],
                                        "arguments": c["args"] or "{}",
                                    },
                                }
                                for idx, c in enumerate(ordered)
                            ],
                        }
                    )
                    for idx, call in enumerate(ordered):
                        name = call["name"]
                        yield f"{TOOL_PREFIX}{name}"
                        try:
                            args = json.loads(call["args"]) if call["args"].strip() else {}
                        except json.JSONDecodeError:
                            args = {}
                        try:
                            result = await session.call_tool(name, args)
                            result_text = call_tool_text(result)
                        except Exception as exc:
                            logger.exception("MCP tool '%s' failed", name)
                            result_text = f"Tool '{name}' failed: {exc}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"] or f"call_{idx}",
                                "content": result_text,
                            }
                        )

                # Tool-round cap hit — return whatever the last round produced.
                logger.warning("Direct API agent hit the %d tool-round cap", MAX_TOOL_ROUNDS)
                yield f"{RESPONSE_PREFIX}{final_text}"

    async def _stream_round(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[tuple[str, str, dict[str, Any]]]:
        """Stream one provider turn.

        Yields `("text", chunk, {})` / `("thinking", chunk, {})` for display and,
        once at the end, `("tool_calls", "", calls)` where `calls` maps tool-call
        index → `{"id", "name", "args"}` (empty when the model gave a final answer).
        """
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
        if self._max_tokens:
            body["max_tokens"] = self._max_tokens
        body.update(self._extra_body())
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers())

        tool_calls: dict[Any, Any] = {}
        async with client.stream(
            "POST", f"{self._base_url}/chat/completions", json=body, headers=headers
        ) as response:
            self._http_response = response
            if response.status_code >= 400:
                raw = (await response.aread()).decode("utf-8", "replace")[:1000]
                detail = _extract_provider_error(raw)
                logger.error("Provider API returned HTTP %s: %s", response.status_code, detail)
                raise ProviderAPIError(response.status_code, detail)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield ("text", content, {})
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    yield ("thinking", reasoning, {})
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_calls.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]

        self._http_response = None
        yield ("tool_calls", "", tool_calls)


class OpenAIPlatformAgent(OpenAICompatibleAgent):
    """Direct API agent preset for OpenAI's platform (``api.openai.com``).

    Functionally identical to :class:`OpenAICompatibleAgent` — same in-process
    tool loop and ``/chat/completions`` plumbing. It exists only so the admin UI
    can offer a first-class "OpenAI Platform" entry whose form is pre-filled with
    OpenAI's base URL, instead of making the admin discover the generic
    OpenAI-compatible (Custom) option and type the URL by hand.
    """

    def get_name(self) -> str:
        return "OpenAI Platform"


class ClaudeConsoleAgent(OpenAICompatibleAgent):
    """Direct API agent preset for Claude Console keys (``console.anthropic.com``).

    Targets Anthropic's OpenAI-compatible endpoint
    (``https://api.anthropic.com/v1/chat/completions``), so it reuses the
    OpenAI-compatible loop unchanged — the Anthropic API key is sent as a Bearer
    token. Like :class:`OpenAIPlatformAgent`, this subclass only carves out a
    pre-filled UI entry; there is no Anthropic-specific request building here.
    """

    def get_name(self) -> str:
        return "Claude Console"


class OllamaAgent(OpenAICompatibleAgent):
    """Direct API agent targeting a self-hosted Ollama OpenAI-compatible API.

    Identical to `OpenAICompatibleAgent` except it needs no API key — a local
    Ollama server accepts unauthenticated requests.
    """

    REQUIRES_API_KEY = False

    def get_name(self) -> str:
        return "Local LLM with Ollama"


class OpenRouterAgent(OpenAICompatibleAgent):
    """Direct API agent targeting the OpenRouter gateway (Option 5).

    OpenRouter exposes one OpenAI-compatible endpoint routing to 100+ models; the
    model is just a config string (e.g. "anthropic/claude-sonnet-4-5"). Identical
    to OpenAICompatibleAgent except it sends OpenRouter's recommended attribution
    headers.
    """

    def get_name(self) -> str:
        return "OpenRouter (Gateway)"

    def _extra_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if OPENROUTER_REFERER:
            headers["HTTP-Referer"] = OPENROUTER_REFERER
        if OPENROUTER_TITLE:
            headers["X-Title"] = OPENROUTER_TITLE
        return headers
