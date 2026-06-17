from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx

from .base import BaseAgent
from .gateway import gateway_auth_headers
from .history import messages_to_prompt
from .mcp_filter import (
    clear_filter,
    register_filter,
    tokenized_mcp_url,
)
from .stream import ERROR_PREFIX, RESPONSE_PREFIX, THINKING_PREFIX, TOOL_PREFIX

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models import AgentConfiguration

CODEX_HTTP_CONNECT_TIMEOUT = float(os.getenv("CODEX_HTTP_CONNECT_TIMEOUT", "30"))
CODEX_HTTP_RESPONSE_TIMEOUT = float(os.getenv("CODEX_HTTP_RESPONSE_TIMEOUT", "300"))


class CodexAgent(BaseAgent):
    """Agent implementation that delegates to the codex Docker service.

    Django POSTs chat requests to the codex service (resolved from
    SystemConfiguration["codex_service_url"] or the CODEX_SERVICE_URL env var),
    which spawns the Codex CLI subprocess internally and streams SSE back.
    """

    def __init__(self, config: AgentConfiguration | None = None) -> None:
        self._config = config
        self._system_prompt = config.system_prompt if config else ""
        self._auth_token = config.auth_token if config else ""

        # Per-agent service_url override (falls back to system config / env below)
        config_service_url = getattr(config, "service_url", "") or "" if config else ""

        from engine.services import SystemConfigService, get

        db_service_url = get(SystemConfigService).get_value("codex_service_url", "") or ""
        self._service_url = (
            config_service_url or db_service_url or os.getenv("CODEX_SERVICE_URL", "")
        ).rstrip("/")
        if not self._service_url:
            raise RuntimeError(
                "CodexAgent requires a service URL. Set the `codex_service_url` system "
                "configuration value or the CODEX_SERVICE_URL environment variable."
            )
        self._http_response: httpx.Response | None = None

    def _apply_credentials(self, payload: dict[str, object]) -> None:
        """Attach this agent's credential to the request payload.

        Overridden by subclasses that authenticate differently (e.g. an API key
        instead of a ChatGPT subscription auth.json).
        """
        if self._auth_token:
            payload["auth_token"] = self._auth_token

    async def cancel(self) -> None:
        """Cancel the running agent task by closing the HTTP stream."""
        if self._http_response is not None:
            try:
                await self._http_response.aclose()
            except Exception:
                pass
            self._http_response = None

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
        custom_mcp_servers: list[dict[str, object]] | None = None,
        history: list[dict[str, str]] | None = None,
        allowed_codebases: list[str] | None = None,
        allowed_reports: list[str] | None = None,
        allowed_dashboards: list[str] | None = None,
        allowed_tethers: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Send message to the codex service and stream response."""
        response_timeout = timeout or CODEX_HTTP_RESPONSE_TIMEOUT

        # The Codex CLI takes a single prompt string, so prior turns are
        # flattened into the message (preserving the consumer's old behavior).
        history_text = messages_to_prompt(history)
        if history_text:
            message = history_text + "\n\n" + message

        logger.debug(
            "chat called: allowed_tools=%s, allowed_databases=%s, allowed_doc_sources=%s, custom_mcp_servers=%s",  # noqa: E501
            allowed_tools,
            allowed_databases,
            allowed_doc_sources,
            [s.get("name") for s in custom_mcp_servers] if custom_mcp_servers else None,
        )

        payload: dict[str, object] = {
            "message": message,
            "session_id": session_id,
            "user_id": user_id,
        }
        instructions = self._system_prompt or ""
        if instructions.strip():
            payload["instructions"] = instructions
        if allowed_tools is not None:
            payload["allowed_tools"] = allowed_tools
        if allowed_databases is not None:
            payload["allowed_databases"] = allowed_databases
        if allowed_doc_sources is not None:
            payload["allowed_doc_sources"] = allowed_doc_sources
        if allowed_codebases is not None:
            payload["allowed_codebases"] = allowed_codebases
        if allowed_reports is not None:
            payload["allowed_reports"] = allowed_reports
        if allowed_dashboards is not None:
            payload["allowed_dashboards"] = allowed_dashboards
        if allowed_tethers is not None:
            payload["allowed_tethers"] = allowed_tethers
        if custom_mcp_servers:
            payload["custom_mcp_servers"] = custom_mcp_servers

        self._apply_credentials(payload)

        # Per-agent model + reasoning effort overrides (stored in the agent's
        # settings JSON). Forwarded to the gateway as `codex exec -c` overrides;
        # omitted entirely when unset so Codex keeps its built-in defaults.
        agent_settings = getattr(self._config, "settings", None) or {}
        if isinstance(agent_settings, dict):
            model = (agent_settings.get("model") or "").strip()
            if model:
                payload["model"] = model
            reasoning_effort = (agent_settings.get("reasoning_effort") or "").strip()
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort

        if max_row_limit is not None:
            payload["max_row_limit"] = str(max_row_limit)

        # Register the per-request MCP filter here (agent-agnostic) and hand the
        # codex service a ready-tokenized MCP URL. A token is ALWAYS registered —
        # even for an unrestricted request (all-None filters = all-access) —
        # because the MCP server fails closed and rejects any untokenized /mcp
        # request. This stops the spawned CLI from reaching a bare, unrestricted
        # endpoint and bypassing its role's filter. The token is cleared in the
        # `finally` below on completion / error / cancel; the MCP server's TTL is
        # the safety net if that clear is missed.
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
                "\n\nUnable to reach the MCP server for security filter registration. "
                "The service may be starting up or temporarily unavailable."
            )
            return
        except httpx.TimeoutException:
            logger.error("Timeout registering filter with MCP server")
            yield "\n\nThe MCP server is not responding. Please try again in a moment."
            return
        except httpx.HTTPStatusError as e:
            logger.error("MCP filter registration returned HTTP %s", e.response.status_code)
            yield (
                "\n\nFailed to register security filters with the MCP server. "
                "Please try again or contact your administrator."
            )
            return
        except Exception:
            logger.exception("Unexpected error during MCP filter registration")
            yield (
                "\n\nAn unexpected error occurred while setting up security filters. "
                "Please try again."
            )
            return
        payload["mcp_url"] = tokenized_mcp_url(filter_token)
        # Exposed so the consumer can fetch this turn's (token-scoped) tool calls.
        self._last_filter_token = filter_token

        try:
            async with asyncio.timeout(response_timeout):
                http_timeout = httpx.Timeout(
                    connect=CODEX_HTTP_CONNECT_TIMEOUT,
                    read=None,
                    write=30,
                    pool=30,
                )
                async with httpx.AsyncClient(timeout=http_timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self._service_url}/chat",
                        json=payload,
                        headers=gateway_auth_headers(),
                    ) as response:
                        self._http_response = response
                        try:
                            response.raise_for_status()
                            async for line in response.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                data = line[len("data:") :].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    event = json.loads(data)
                                    if isinstance(event, dict):
                                        event_type = event.get("type", "")
                                        if event_type == "tool_call":
                                            name = event.get("name", "")
                                            if name:
                                                yield f"{TOOL_PREFIX}{name}"
                                        elif event_type == "response":
                                            yield f"{RESPONSE_PREFIX}{event.get('text', '')}"
                                        elif event_type == "thinking":
                                            yield f"{THINKING_PREFIX}{event.get('text', '')}"
                                        elif event_type == "error_detail":
                                            yield f"{ERROR_PREFIX}{event.get('text', '')}"
                                        elif event_type == "text":
                                            yield event.get("text", "")
                                        else:
                                            yield event.get("text", "")
                                    else:
                                        yield str(event)
                                except json.JSONDecodeError:
                                    yield data
                        except httpx.HTTPStatusError as e:
                            logger.error(
                                "Codex service returned HTTP %s: %s",
                                e.response.status_code,
                                e,
                            )
                            yield (
                                "\n\nThe AI service returned an error. "
                                "Please try again or contact your administrator."
                            )
                        finally:
                            self._http_response = None
        except httpx.ConnectError:
            logger.error("Cannot connect to Codex service at %s", self._service_url)
            yield (
                "\n\nUnable to reach the AI service. "
                "The service may be starting up or temporarily unavailable."
            )
        except httpx.TimeoutException:
            logger.error("Timeout connecting to Codex service at %s", self._service_url)
            yield ("\n\nThe AI service is not responding. Please try again in a moment.")
        except httpx.ReadError:
            logger.warning("Connection to Codex service interrupted")
            yield (
                "\n\nThe connection to the AI service was interrupted. "
                "Please try sending your message again."
            )
        except TimeoutError:
            logger.error(
                "Overall response timeout (%ss) exceeded for Codex HTTP request",
                response_timeout,
            )
            yield (
                "\n\nThe response timed out. Your query may be too complex — "
                "try simplifying it or breaking it into smaller questions."
            )
        finally:
            # Runs on normal completion, error, and cancellation (when the
            # consumer closes the HTTP stream, the `async for` above raises
            # and unwinds through here).
            if filter_token:
                await clear_filter(filter_token)

    def supports_mcp(self) -> bool:
        return True

    def get_name(self) -> str:
        return "Codex CLI (HTTP service)"


class CodexApiAgent(CodexAgent):
    """Codex CLI agent authenticated by a provider API key instead of an
    auth.json subscription credential.

    Reuses the entire CodexAgent streaming/MCP-filter pipeline; only the
    credential and the service URL resolution differ. The gateway injects the
    API key as an env var for the `codex exec` subprocess (no auth.json seeding).
    """

    def __init__(self, config: AgentConfiguration | None = None) -> None:
        self._config = config
        self._system_prompt = config.system_prompt if config else ""
        # API-key auth never uses the auth.json credential.
        self._auth_token = ""
        self._api_key = config.api_key if config else ""

        # Resolve the service URL with a distinct fallback chain so this agent
        # never routes to the auth-token Codex container by accident.
        config_service_url = (getattr(config, "service_url", "") or "") if config else ""

        from engine.services import SystemConfigService, get

        db_service_url = get(SystemConfigService).get_value("codex_api_service_url", "") or ""
        self._service_url = (
            config_service_url or db_service_url or os.getenv("CODEX_API_SERVICE_URL", "")
        ).rstrip("/")
        if not self._service_url:
            raise RuntimeError(
                "CodexApiAgent requires a service URL. Set this agent's service URL, "
                "the `codex_api_service_url` system configuration value, or the "
                "CODEX_API_SERVICE_URL environment variable."
            )
        self._http_response: httpx.Response | None = None

    def _apply_credentials(self, payload: dict[str, object]) -> None:
        if self._api_key:
            payload["api_key"] = self._api_key

    def get_name(self) -> str:
        return "Codex CLI (API key)"
