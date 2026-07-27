"""Per-surface chat tool allow-lists (``engine.chat_surfaces``).

Each chat surface exposes only a curated subset of the built-in MCP tools. These
tests pin the main-chat allow-list (read-only: no write tools), the closed
chart-edit set, and the two filtering rules that matter — built-in write tools
are dropped, and custom (non-built-in) MCP server tools pass through untouched.
"""

from __future__ import annotations

from engine.chat_surfaces import (
    ChatSurface,
    filter_surface_tools,
    is_callable,
    surface_tools,
)

# Built-in write tools that must never be reachable from the main chat.
WRITE_TOOLS = {
    "create_documentation",
    "create_dashboard",
    "add_chart",
    "update_chart",
    "save_tether_graph",
}


def test_main_surface_is_read_only() -> None:
    main = surface_tools(ChatSurface.MAIN)
    assert WRITE_TOOLS.isdisjoint(main)
    # A representative read tool is present.
    assert "query_database" in main
    assert "search_docs" in main


def test_chart_edit_surface_owns_update_chart() -> None:
    assert surface_tools(ChatSurface.CHART_EDIT) == {
        "update_chart",
        "query_database",
        "list_tables",
        "get_table_schema",
        "list_databases",
        "search_docs",
    }


def test_filter_main_drops_write_tools_keeps_reads() -> None:
    candidates = [
        "query_database",
        "add_chart",
        "update_chart",
        "save_tether_graph",
        "list_tables",
    ]
    assert filter_surface_tools(ChatSurface.MAIN, candidates) == [
        "query_database",
        "list_tables",
    ]


def test_filter_main_passes_custom_server_tools_through() -> None:
    # A tool name outside the built-in universe (i.e. from a user-defined custom
    # MCP server) is not gated by the surface allow-list.
    assert filter_surface_tools(ChatSurface.MAIN, ["query_database", "tool_from_custom_mcp"]) == [
        "query_database",
        "tool_from_custom_mcp",
    ]


def test_is_callable_per_surface() -> None:
    assert is_callable(ChatSurface.MAIN, "query_database") is True
    assert is_callable(ChatSurface.MAIN, "update_chart") is False
    assert is_callable(ChatSurface.CHART_EDIT, "update_chart") is True
    # Custom-server tool: callable on any surface.
    assert is_callable(ChatSurface.MAIN, "tool_from_custom_mcp") is True
