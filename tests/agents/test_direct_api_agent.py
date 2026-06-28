"""Direct API agent (Option 3).

The agent runs the tool-call loop in-process: it streams an OpenAI-compatible
provider, executes MCP tool calls, and feeds results back until a final answer.
Both the provider stream and the MCP session are faked (``_fakes`` /
``conftest``) so no network is involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from engine.agents import direct_api
from engine.agents.direct_api import (
    ClaudeConsoleAgent,
    OpenAICompatibleAgent,
    OpenAIPlatformAgent,
    OpenRouterAgent,
    ProviderAPIError,
    _root_cause,
)
from engine.agents.stream import TOOL_PREFIX, parse_chunk

from ._fakes import FakeConfig, FakeSession, FakeStreamResponse, collect, make_fake_client


async def test_tool_loop_runs_then_answers(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession, patch_mcp: Any
) -> None:
    """A tool-call round executes the MCP tool, then a final answer is emitted."""
    patch_mcp(fake_session)

    round1 = _sse_tool_call_in_fragments()
    round2 = _sse(
        {"choices": [{"delta": {"content": "Tables: "}}]},
        {"choices": [{"delta": {"content": "users, orders"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    )
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", make_fake_client([round1, round2]))

    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig()))
    chunks = await collect(agent.chat("list tables", user_id=1, session_id="s1"))

    # Tool call surfaced, with fragmented arguments correctly reassembled.
    assert f"{TOOL_PREFIX}list_tables" in chunks
    assert fake_session.calls == [("list_tables", {"database": "db1"})]

    # Plain deltas streamed for live typing.
    texts = [c for c in chunks if parse_chunk(c).kind == "text"]
    assert "".join(texts) == "Tables: users, orders"

    # Exactly one canonical final answer.
    responses = [parse_chunk(c).text for c in chunks if parse_chunk(c).kind == "response"]
    assert responses == ["Tables: users, orders"]


async def test_history_is_sent_as_turns(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession, patch_mcp: Any
) -> None:
    """Structured history becomes prior user/assistant messages on the request."""
    patch_mcp(fake_session)
    captured: dict[str, Any] = {}
    fake_cls = _capturing_client(captured, "messages", lambda j: j["messages"])
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", fake_cls)

    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig()))
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await collect(agent.chat("now this", user_id=1, session_id="s1", history=history))

    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "now this"


async def test_missing_model_yields_config_error() -> None:
    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig(model="")))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert len(chunks) == 1
    assert "not fully configured" in chunks[0]


async def test_missing_api_key_yields_config_error() -> None:
    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig(api_key="")))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert len(chunks) == 1
    assert "no API key" in chunks[0]


async def test_provider_connection_error_is_friendly(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession, patch_mcp: Any
) -> None:
    """A transport error yields a user-facing message, never raises."""
    patch_mcp(fake_session)
    monkeypatch.setattr(
        direct_api.httpx,
        "AsyncClient",
        make_fake_client([], raise_exc=httpx.ConnectError("down")),
    )

    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig()))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert any("Unable to reach the AI provider" in c for c in chunks)


async def test_provider_http_error_surfaces_detail(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession, patch_mcp: Any
) -> None:
    """A 4xx from the provider yields a friendly chunk AND an ERROR marker whose
    text carries the provider's parsed message, so the consumer persists the real
    cause (e.g. an invalid model) to the session log."""
    patch_mcp(fake_session)

    class ErrorResponse(FakeStreamResponse):
        def __init__(self) -> None:
            super().__init__([], status_code=404)

        async def aread(self) -> bytes:
            return b'{"error":{"type":"invalid_request_error","message":"model: haiku"}}'

    fake_cls = make_fake_client([])
    fake_cls.stream = lambda self, *a, **k: ErrorResponse()  # type: ignore[assignment]
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", fake_cls)

    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig()))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))

    # User-facing friendly message present (never raises).
    assert any("rejected the request" in c for c in chunks)
    # Real cause surfaced via the ERROR marker for session-log persistence.
    errors = [parse_chunk(c).text for c in chunks if parse_chunk(c).kind == "error"]
    assert errors and "model: haiku" in errors[0] and "404" in errors[0]


def test_root_cause_unwraps_exception_groups() -> None:
    """ExceptionGroups (from the MCP task group) are drilled to the leaf cause so
    the real error is classified instead of collapsing to the generic path."""
    leaf = ProviderAPIError(404, "model: haiku")
    grouped = ExceptionGroup("outer", [ExceptionGroup("inner", [leaf])])
    assert _root_cause(grouped) is leaf
    assert _root_cause(leaf) is leaf


async def test_openrouter_sends_attribution_headers(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession, patch_mcp: Any
) -> None:
    """OpenRouterAgent merges HTTP-Referer / X-Title into the provider request."""
    patch_mcp(fake_session)
    captured: dict[str, Any] = {}
    fake_cls = _capturing_client(captured, "headers", lambda _j: None, capture_headers=True)
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", fake_cls)

    agent = OpenRouterAgent(
        config=cast(
            Any,
            FakeConfig(
                model="anthropic/claude-sonnet-4-5", base_url="https://openrouter.ai/api/v1"
            ),
        )
    )
    assert agent.get_name() == "OpenRouter (Gateway)"
    await collect(agent.chat("hi", user_id=1, session_id="s1"))

    assert captured["headers"]["X-Title"] == direct_api.OPENROUTER_TITLE
    assert captured["headers"]["HTTP-Referer"] == direct_api.OPENROUTER_REFERER
    # Auth header still injected from the API key.
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_build_agent_maps_openrouter() -> None:
    """The factory resolves the openrouter type to OpenRouterAgent."""
    from engine.agents import build_agent

    config = cast(
        Any,
        SimpleNamespace(
            agent_type="openrouter",
            system_prompt="",
            settings={"model": "openai/gpt-4o", "base_url": "https://openrouter.ai/api/v1"},
            api_key="sk-test",
        ),
    )
    assert isinstance(build_agent(config), OpenRouterAgent)


def test_build_agent_maps_direct_api_presets() -> None:
    """The factory resolves the OpenAI Platform / Claude Console presets, which
    share the OpenAICompatibleAgent backend but carry their own display names."""
    from engine.agents import build_agent

    def make(agent_type: str, base_url: str) -> Any:
        return cast(
            Any,
            SimpleNamespace(
                agent_type=agent_type,
                system_prompt="",
                settings={"model": "x", "base_url": base_url},
                api_key="sk-test",
            ),
        )

    platform = build_agent(make("openai_platform", "https://api.openai.com/v1"))
    assert isinstance(platform, OpenAIPlatformAgent)
    assert isinstance(platform, OpenAICompatibleAgent)
    assert platform.get_name() == "OpenAI Platform"

    console = build_agent(make("claude_console", "https://api.anthropic.com/v1"))
    assert isinstance(console, ClaudeConsoleAgent)
    assert isinstance(console, OpenAICompatibleAgent)
    assert console.get_name() == "Claude Console"


async def test_cancel_closes_stream() -> None:
    agent = OpenAICompatibleAgent(config=cast(Any, FakeConfig()))
    fake_resp = FakeStreamResponse([])
    agent._http_response = cast(Any, fake_resp)
    await agent.cancel()
    assert fake_resp.closed is True
    assert agent._http_response is None


# --- local SSE builders -----------------------------------------------------


def _sse(*objs: dict[str, Any]) -> list[str]:
    from ._fakes import sse

    return sse(*objs)


def _tool_call_delta(
    *, arguments: str, name: str | None = None, call_id: str | None = None
) -> dict[str, Any]:
    """One streaming choice carrying a (possibly partial) tool call.

    ``name``/``arguments`` sit inside ``function``; ``id`` is a sibling — only the
    first fragment of a call carries the name and id.
    """
    function: dict[str, Any] = {"arguments": arguments}
    if name is not None:
        function["name"] = name
    call: dict[str, Any] = {"index": 0, "function": function}
    if call_id is not None:
        call["id"] = call_id
    return {"choices": [{"delta": {"tool_calls": [call]}}]}


def _sse_tool_call_in_fragments() -> list[str]:
    """One tool call whose JSON arguments arrive split across three deltas."""
    return _sse(
        _tool_call_delta(name="list_tables", arguments="", call_id="call_1"),
        _tool_call_delta(arguments='{"database"'),
        _tool_call_delta(arguments=':"db1"}'),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    )


def _capturing_client(
    captured: dict[str, Any],
    key: str,
    extract: Any,
    *,
    capture_headers: bool = False,
) -> type[Any]:
    """A fake client that records part of the outgoing request, then replays one
    short ``ok``/``stop`` round so ``chat`` completes."""
    from ._fakes import FakeStreamResponse

    round1 = _sse(
        {"choices": [{"delta": {"content": "ok"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    )
    fake_cls = make_fake_client([round1])
    orig_stream = fake_cls.stream

    def capturing_stream(
        self: Any,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeStreamResponse:
        captured[key] = headers if capture_headers else extract(json)
        return cast(FakeStreamResponse, orig_stream(self, method, url, json=json, headers=headers))

    fake_cls.stream = capturing_stream  # type: ignore[assignment]
    return fake_cls
