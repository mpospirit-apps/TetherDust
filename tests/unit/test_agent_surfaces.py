"""Per-surface tool allow-lists (``engine.agent_surfaces``).

Each agent surface (chat, chart-edit, and the three generation flows) exposes
only a curated subset of the built-in MCP tools. These tests pin the principle —
read tools shared broadly, write tools surface-exclusive — plus the two filtering
rules that matter: built-in tools outside a surface's set are dropped, and custom
(non-built-in) MCP server tools pass through open surfaces only.
"""

from __future__ import annotations

from engine.agent_surfaces import (
    AgentSurface,
    callable_surfaces,
    filter_surface_tools,
    is_callable,
    surface_tools,
)

CODEBASE_READS = {
    "list_codebases",
    "get_codebase_tree",
    "read_codebase_file",
    "search_codebase",
}
WRITE_TOOLS = {
    "create_documentation",
    "create_dashboard",
    "add_chart",
    "update_chart",
    "save_tether_graph",
}


def test_chat_is_read_only() -> None:
    chat = surface_tools(AgentSurface.CHAT)
    assert WRITE_TOOLS.isdisjoint(chat)
    assert {"query_database", "search_docs", "list_reports"} <= chat


def test_chart_edit_owns_update_chart() -> None:
    assert surface_tools(AgentSurface.CHART_EDIT) == {
        "update_chart",
        "query_database",
        "list_tables",
        "get_table_schema",
        "list_databases",
        "search_docs",
    }


def test_doc_gen_has_codebase_reads_and_only_its_write() -> None:
    doc = surface_tools(AgentSurface.DOC_GEN)
    assert CODEBASE_READS <= doc
    assert "create_documentation" in doc
    assert doc & WRITE_TOOLS == {"create_documentation"}


def test_dashboard_gen_reads_dashboards_and_only_its_writes() -> None:
    dash = surface_tools(AgentSurface.DASHBOARD_GEN)
    assert {"list_dashboards", "get_dashboard_charts"} <= dash
    assert dash & WRITE_TOOLS == {"create_dashboard", "add_chart"}
    assert CODEBASE_READS.isdisjoint(dash)


def test_tether_gen_has_codebase_reads_and_only_its_write() -> None:
    tether = surface_tools(AgentSurface.TETHER_GEN)
    assert CODEBASE_READS <= tether
    assert tether & WRITE_TOOLS == {"save_tether_graph"}


def test_callable_surfaces_matrix() -> None:
    assert callable_surfaces("query_database") == list(AgentSurface)  # all 5
    assert callable_surfaces("save_tether_graph") == [AgentSurface.TETHER_GEN]
    assert callable_surfaces("create_documentation") == [AgentSurface.DOC_GEN]
    assert callable_surfaces("update_chart") == [AgentSurface.CHART_EDIT]
    assert callable_surfaces("search_codebase") == [
        AgentSurface.CHAT,
        AgentSurface.DOC_GEN,
        AgentSurface.TETHER_GEN,
    ]


def test_custom_tool_callable_only_on_open_surfaces() -> None:
    # A tool outside the built-in universe (from a user-defined custom MCP server)
    # is callable on open surfaces, never on the closed chart-edit surface.
    assert is_callable(AgentSurface.CHAT, "tool_from_custom_mcp") is True
    assert is_callable(AgentSurface.DOC_GEN, "tool_from_custom_mcp") is True
    assert is_callable(AgentSurface.CHART_EDIT, "tool_from_custom_mcp") is False


def test_filter_drops_out_of_surface_builtins_keeps_custom() -> None:
    # Doc gen: keeps its reads + create_documentation + custom tool; drops another
    # surface's write tool (save_tether_graph) and out-of-surface reads (reports).
    candidates = [
        "query_database",
        "search_codebase",
        "list_reports",
        "save_tether_graph",
        "create_documentation",
        "tool_from_custom_mcp",
    ]
    assert filter_surface_tools(AgentSurface.DOC_GEN, candidates) == [
        "query_database",
        "search_codebase",
        "create_documentation",
        "tool_from_custom_mcp",
    ]
