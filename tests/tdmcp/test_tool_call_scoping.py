"""Tool-call tracking is scoped per request token, not a global buffer.

Previously the MCP server recorded tool calls in one global list, so concurrent
chats drained/attributed each other's calls. Now each request records under its
filter token; a turn fetches only its own.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun import freeze_time

from tdmcp import server


def test_calls_are_isolated_per_token(record_tool_calls: Any) -> None:
    """Interleaved requests don't see each other's tool calls."""
    record_tool_calls("tokA", "list_tables", "query_database")
    record_tool_calls("tokB", "search_docs")
    record_tool_calls("tokA", "get_table_schema")  # second batch on A after B

    assert server._drain_tool_calls("tokA") == ["list_tables", "query_database", "get_table_schema"]
    assert server._drain_tool_calls("tokB") == ["search_docs"]


def test_drain_is_one_shot_and_dedupes(record_tool_calls: Any) -> None:
    record_tool_calls("tokC", "query_database", "query_database")  # duplicate
    assert server._drain_tool_calls("tokC") == ["query_database"]  # deduped
    assert server._drain_tool_calls("tokC") == []  # already drained


def test_untracked_when_no_token() -> None:
    """A request with no token (e.g. stdio) records nothing."""
    server._record_tool_call("list_tables")  # no token set in context
    assert server._drain_tool_calls("") == []


def test_unknown_token_returns_empty() -> None:
    assert server._drain_tool_calls("never-registered") == []


def test_ttl_purges_stale_buffers(record_tool_calls: Any) -> None:
    with freeze_time("2026-01-01T00:00:00Z") as frozen:
        record_tool_calls("tokOld", "list_tables")
        frozen.tick(timedelta(seconds=server._TOOL_CALLS_TTL_SECONDS + 100))
        server._purge_expired_tool_calls()
    assert server._drain_tool_calls("tokOld") == []


async def test_fetch_tools_called_requires_token() -> None:
    """The Django client returns [] (no network call) when no token is given."""
    from engine.consumers.mcp_client import fetch_tools_called

    assert await fetch_tools_called(None) == []
    assert await fetch_tools_called("") == []
