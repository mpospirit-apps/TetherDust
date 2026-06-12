"""Tests for the Direct API agent (Option 3).

The agent runs the tool-call loop in-process: it streams an OpenAI-compatible
provider, executes MCP tool calls, and feeds results back until a final answer.
These tests mock both the provider stream and the MCP session so no network or
Django setup is needed — the agent module has no Django imports at load time.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx

# The agent lives in the Django web app; add it to the path (no Django settings
# are required to import the module).
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from core.agents import direct_api  # noqa: E402
from core.agents.direct_api import (  # noqa: E402
    ClaudeConsoleAgent,
    OpenAICompatibleAgent,
    OpenAIPlatformAgent,
    OpenRouterAgent,
    ProviderAPIError,
    _root_cause,
)
from core.agents.stream import TOOL_PREFIX, parse_chunk  # noqa: E402

# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeConfig:
    """Duck-typed stand-in for AgentConfiguration."""

    def __init__(self, model="gpt-4o", base_url="https://api.test/v1", api_key="sk-test"):
        self.system_prompt = "You are a test agent."
        self.settings = {"model": model, "base_url": base_url}
        self._api_key = api_key

    def get_api_key(self):
        return self._api_key


class FakeSession:
    """Minimal MCP ClientSession: one tool, records call_tool invocations."""

    def __init__(self):
        self.calls = []

    async def list_tools(self):
        tool = SimpleNamespace(
            name="list_tables",
            description="List tables",
            inputSchema={"type": "object", "properties": {"database": {"type": "string"}}},
        )
        return SimpleNamespace(tools=[tool])

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text="users, orders")])


class FakeStreamResponse:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code
        self.request = SimpleNamespace()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b'{"error": "boom"}'

    async def aclose(self):
        self.closed = True


def make_fake_client(rounds, raise_exc=None):
    """Build a fake httpx.AsyncClient class that replays `rounds` of SSE lines."""
    queue = list(rounds)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, json=None, headers=None):
            if raise_exc is not None:
                raise raise_exc
            return FakeStreamResponse(queue.pop(0))

        # The agent always registers (POST) a per-request MCP filter token and
        # clears it (DELETE) afterwards, before/after the provider stream. These
        # succeed regardless of `raise_exc`, which targets the provider stream
        # only — so transport-error tests still exercise the stream path.
        async def post(self, url, json=None, headers=None):
            return SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"status": "registered"},
            )

        async def delete(self, url, headers=None):
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    return FakeAsyncClient


def sse(*objs):
    """Render dicts as provider SSE `data:` lines, terminated by [DONE]."""
    import json

    return [f"data: {json.dumps(o)}" for o in objs] + ["data: [DONE]"]


async def collect(agen):
    return [chunk async for chunk in agen]


def patch_mcp(monkeypatch, session):
    @asynccontextmanager
    async def fake_open(url, headers=None):
        yield session

    monkeypatch.setattr(direct_api, "open_mcp_session", fake_open)


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_tool_loop_runs_then_answers(monkeypatch):
    """A tool-call round executes the MCP tool, then a final answer is emitted."""
    session = FakeSession()
    patch_mcp(monkeypatch, session)

    round1 = sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "list_tables", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"database"'}}]}}
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ':"db1"}'}}]}}
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    )
    round2 = sse(
        {"choices": [{"delta": {"content": "Tables: "}}]},
        {"choices": [{"delta": {"content": "users, orders"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    )
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", make_fake_client([round1, round2]))

    agent = OpenAICompatibleAgent(config=FakeConfig())
    chunks = await collect(agent.chat("list tables", user_id=1, session_id="s1"))

    # Tool call surfaced, with fragmented arguments correctly reassembled.
    assert f"{TOOL_PREFIX}list_tables" in chunks
    assert session.calls == [("list_tables", {"database": "db1"})]

    # Plain deltas streamed for live typing.
    texts = [c for c in chunks if parse_chunk(c).kind == "text"]
    assert "".join(texts) == "Tables: users, orders"

    # Exactly one canonical final answer.
    responses = [parse_chunk(c).text for c in chunks if parse_chunk(c).kind == "response"]
    assert responses == ["Tables: users, orders"]


async def test_history_is_sent_as_turns(monkeypatch):
    """Structured history becomes prior user/assistant messages on the request."""
    session = FakeSession()
    patch_mcp(monkeypatch, session)

    captured = {}

    round1 = sse(
        {"choices": [{"delta": {"content": "ok"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    )

    fake_cls = make_fake_client([round1])
    orig_stream = fake_cls.stream

    def capturing_stream(self, method, url, json=None, headers=None):
        captured["messages"] = json["messages"]
        return orig_stream(self, method, url, json=json, headers=headers)

    fake_cls.stream = capturing_stream
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", fake_cls)

    agent = OpenAICompatibleAgent(config=FakeConfig())
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await collect(agent.chat("now this", user_id=1, session_id="s1", history=history))

    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "now this"


async def test_missing_model_yields_config_error(monkeypatch):
    agent = OpenAICompatibleAgent(config=FakeConfig(model=""))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert len(chunks) == 1
    assert "not fully configured" in chunks[0]


async def test_missing_api_key_yields_config_error(monkeypatch):
    agent = OpenAICompatibleAgent(config=FakeConfig(api_key=""))
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert len(chunks) == 1
    assert "no API key" in chunks[0]


async def test_provider_connection_error_is_friendly(monkeypatch):
    """A transport error yields a user-facing message, never raises."""
    session = FakeSession()
    patch_mcp(monkeypatch, session)
    monkeypatch.setattr(
        direct_api.httpx,
        "AsyncClient",
        make_fake_client([], raise_exc=httpx.ConnectError("down")),
    )

    agent = OpenAICompatibleAgent(config=FakeConfig())
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))
    assert any("Unable to reach the AI provider" in c for c in chunks)


async def test_provider_http_error_surfaces_detail(monkeypatch):
    """A 4xx from the provider yields a friendly chunk AND an ERROR marker whose
    text carries the provider's parsed message, so the consumer persists the real
    cause (e.g. an invalid model) to the session log."""
    session = FakeSession()
    patch_mcp(monkeypatch, session)

    class ErrorResponse(FakeStreamResponse):
        def __init__(self):
            super().__init__([], status_code=404)

        async def aread(self):
            return b'{"error":{"type":"invalid_request_error","message":"model: haiku"}}'

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        def stream(self, *a, **k):
            return ErrorResponse()

        async def post(self, *a, **k):
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        async def delete(self, *a, **k):
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(direct_api.httpx, "AsyncClient", FakeAsyncClient)

    agent = OpenAICompatibleAgent(config=FakeConfig())
    chunks = await collect(agent.chat("hi", user_id=1, session_id="s1"))

    # User-facing friendly message present (never raises).
    assert any("rejected the request" in c for c in chunks)
    # Real cause surfaced via the ERROR marker for session-log persistence.
    errors = [parse_chunk(c).text for c in chunks if parse_chunk(c).kind == "error"]
    assert errors and "model: haiku" in errors[0] and "404" in errors[0]


def test_root_cause_unwraps_exception_groups():
    """ExceptionGroups (from the MCP task group) are drilled to the leaf cause so
    the real error is classified instead of collapsing to the generic path."""
    leaf = ProviderAPIError(404, "model: haiku")
    grouped = ExceptionGroup("outer", [ExceptionGroup("inner", [leaf])])
    assert _root_cause(grouped) is leaf
    assert _root_cause(leaf) is leaf


async def test_openrouter_sends_attribution_headers(monkeypatch):
    """OpenRouterAgent merges HTTP-Referer / X-Title into the provider request."""
    session = FakeSession()
    patch_mcp(monkeypatch, session)

    captured = {}

    round1 = sse(
        {"choices": [{"delta": {"content": "ok"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    )

    fake_cls = make_fake_client([round1])
    orig_stream = fake_cls.stream

    def capturing_stream(self, method, url, json=None, headers=None):
        captured["headers"] = headers
        return orig_stream(self, method, url, json=json, headers=headers)

    fake_cls.stream = capturing_stream
    monkeypatch.setattr(direct_api.httpx, "AsyncClient", fake_cls)

    agent = OpenRouterAgent(
        config=FakeConfig(
            model="anthropic/claude-sonnet-4-5", base_url="https://openrouter.ai/api/v1"
        )
    )
    assert agent.get_name() == "OpenRouter (Gateway)"
    await collect(agent.chat("hi", user_id=1, session_id="s1"))

    assert captured["headers"]["X-Title"] == direct_api.OPENROUTER_TITLE
    assert captured["headers"]["HTTP-Referer"] == direct_api.OPENROUTER_REFERER
    # Auth header still injected from the API key.
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_build_agent_maps_openrouter():
    """The factory resolves the openrouter type to OpenRouterAgent."""
    from core.agents import build_agent

    config = SimpleNamespace(
        agent_type="openrouter",
        system_prompt="",
        settings={"model": "openai/gpt-4o", "base_url": "https://openrouter.ai/api/v1"},
        get_api_key=lambda: "sk-test",
    )
    agent = build_agent(config)
    assert isinstance(agent, OpenRouterAgent)


def test_build_agent_maps_direct_api_presets():
    """The factory resolves the OpenAI Platform / Claude Console presets, which
    share the OpenAICompatibleAgent backend but carry their own display names."""
    from core.agents import build_agent

    def make(agent_type, base_url):
        return SimpleNamespace(
            agent_type=agent_type,
            system_prompt="",
            settings={"model": "x", "base_url": base_url},
            get_api_key=lambda: "sk-test",
        )

    platform = build_agent(make("openai_platform", "https://api.openai.com/v1"))
    assert isinstance(platform, OpenAIPlatformAgent)
    assert isinstance(platform, OpenAICompatibleAgent)
    assert platform.get_name() == "OpenAI Platform"

    console = build_agent(make("claude_console", "https://api.anthropic.com/v1"))
    assert isinstance(console, ClaudeConsoleAgent)
    assert isinstance(console, OpenAICompatibleAgent)
    assert console.get_name() == "Claude Console"


async def test_cancel_closes_stream():
    agent = OpenAICompatibleAgent(config=FakeConfig())
    fake_resp = FakeStreamResponse([])
    agent._http_response = fake_resp
    await agent.cancel()
    assert fake_resp.closed is True
    assert agent._http_response is None
