"""Per-surface tool allow-lists for the chat agent.

TetherDust exposes the AI agent through several *chat surfaces* — the main chat,
the dashboard chart-edit panel, and (planned) a per-dashboard chat. Each surface
should only be able to invoke a curated subset of the built-in MCP tools: the
main chat is read-only/analytical, the chart-edit panel can also ``update_chart``,
etc. This module is the single source of truth for that mapping, consumed both by
the runtime consumers (which strip disallowed tools before handing the list to
the agent) and by the admin tool list (which flags chat-callability on each card).

The surface allow-list is the *structural* capability of a surface and lives in
code. It composes with the *per-user* ``Role.allowed_tools`` grant (DB):

    effective tools = surface allow-list (here)  ∩  role grants (DB)

Only built-in tools are gated here. Tools from user-defined (custom) MCP servers
are outside the built-in universe and pass through for *open* surfaces (see
``filter_surface_tools``); *closed* surfaces emit their set verbatim instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from engine.builtin_mcp import builtin_tool_names


class ChatSurface(StrEnum):
    MAIN = "main"
    CHART_EDIT = "chart_edit"
    # DASHBOARD = "dashboard"   # future: per-dashboard chat


# Built-in tools each chat surface may invoke. Editing a set here updates both
# runtime enforcement and the admin "callable" badge.
SURFACE_TOOLS: dict[ChatSurface, frozenset[str]] = {
    # Main chat: read-only/analytical. Write tools (create_documentation,
    # create_dashboard, add_chart, update_chart, save_tether_graph) are handled
    # by their own generation surfaces, not free-form chat.
    ChatSurface.MAIN: frozenset(
        {
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            "list_codebases",
            "get_codebase_tree",
            "read_codebase_file",
            "search_codebase",
            "list_reports",
            "get_report_data",
            "list_dashboards",
            "get_dashboard_charts",
            "list_tethers",
            "get_tether_graph",
        }
    ),
    # Chart-edit panel: a closed surface that owns update_chart, plus the read
    # tools it needs to reshape a chart's query. Emitted verbatim (see
    # management/consumers/chart_edit.py) — not intersected with a role.
    ChatSurface.CHART_EDIT: frozenset(
        {
            "update_chart",
            "query_database",
            "list_tables",
            "get_table_schema",
            "list_databases",
            "search_docs",
        }
    ),
}


def surface_tools(surface: ChatSurface) -> frozenset[str]:
    """The built-in tools a surface may invoke."""
    return SURFACE_TOOLS[surface]


def is_callable(
    surface: ChatSurface, tool_name: str, *, builtin_names: set[str] | None = None
) -> bool:
    """Whether ``tool_name`` may be invoked in ``surface``.

    Built-in tools are gated by the surface's allow-list; any non-built-in
    (custom MCP server) tool passes through. Pass ``builtin_names`` to avoid a
    repeated ``tdmcp`` introspection when checking many tools.
    """
    if builtin_names is None:
        builtin_names = builtin_tool_names()
    if tool_name in builtin_names:
        return tool_name in SURFACE_TOOLS[surface]
    return True


def filter_surface_tools(surface: ChatSurface, names: Iterable[str]) -> list[str]:
    """Keep only the tools callable in ``surface``, preserving input order.

    Built-in tools outside the surface's allow-list are dropped; custom MCP
    server tools are kept. Use this on an *open* surface (one that filters an
    externally-supplied candidate list, e.g. a role's grants or every enabled
    tool). A *closed* surface should use ``surface_tools`` directly instead.
    """
    builtin_names = builtin_tool_names()
    return [n for n in names if is_callable(surface, n, builtin_names=builtin_names)]
