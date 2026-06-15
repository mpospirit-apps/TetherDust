"""Tool-call tracking is scoped per request token, not a global buffer.

Previously the MCP server recorded tool calls in one global list, so concurrent
chats drained/attributed each other's calls. Now each request records under its
filter token; a turn fetches only its own.
"""

import sys
from pathlib import Path

import pytest

from tdmcp import server
from tdmcp._context import request_filter_token

# Make the Django-side helper importable without Django settings.
WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))


def _record_under(token: str, *names: str) -> None:
    tok = request_filter_token.set(token)
    try:
        for n in names:
            server._record_tool_call(n)
    finally:
        request_filter_token.reset(tok)


def test_calls_are_isolated_per_token() -> None:
    """Interleaved requests don't see each other's tool calls."""
    _record_under("tokA", "list_tables", "query_database")
    _record_under("tokB", "search_docs")
    # Interleave a second batch on A after B recorded.
    _record_under("tokA", "get_table_schema")

    assert server._drain_tool_calls("tokA") == [
        "list_tables",
        "query_database",
        "get_table_schema",
    ]
    assert server._drain_tool_calls("tokB") == ["search_docs"]


def test_drain_is_one_shot_and_dedupes() -> None:
    _record_under("tokC", "query_database", "query_database")  # duplicate
    assert server._drain_tool_calls("tokC") == ["query_database"]  # deduped
    assert server._drain_tool_calls("tokC") == []  # already drained


def test_untracked_when_no_token() -> None:
    """A request with no token (e.g. stdio) records nothing."""
    server._record_tool_call("list_tables")  # no token set in context
    assert server._drain_tool_calls("") == []


def test_unknown_token_returns_empty() -> None:
    assert server._drain_tool_calls("never-registered") == []


def test_ttl_purges_stale_buffers(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t

    _record_under("tokOld", "list_tables")
    # Fast-forward "now" past the buffer's creation time + TTL, then purge.
    future = _t.time() + server._TOOL_CALLS_TTL_SECONDS + 100
    monkeypatch.setattr(server.time, "time", lambda: future)
    server._purge_expired_tool_calls()
    assert server._drain_tool_calls("tokOld") == []


async def test_fetch_tools_called_requires_token() -> None:
    """The Django client returns [] (no network call) when no token is given."""
    from core.consumers.mcp_client import fetch_tools_called

    assert await fetch_tools_called(None) == []
    assert await fetch_tools_called("") == []
