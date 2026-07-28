"""Per-surface tool allow-lists for the AI agent.

TetherDust invokes the agent through several *surfaces* — the main chat, the
dashboard chart-edit panel, and the doc / dashboard / tether generation flows.
Each surface should only be able to call a curated subset of the built-in MCP
tools: the main chat is read-only/analytical, generation flows can also call
*their own* write tool, etc. This module is the single source of truth for that
mapping, consumed both by the runtime consumers/engines (which strip disallowed
tools before handing the list to the agent) and by the admin tool list (which
shows which surfaces can call each tool).

The general principle: read tools are shared broadly; **write tools are
surface-exclusive** (only doc gen creates docs, only tether gen saves graphs,
only the chart-edit panel updates a chart, …).

A surface allow-list is the *structural* capability of a surface and lives in
code. For the interactive chat it composes with the *per-user*
``Role.allowed_tools`` grant (DB): effective = surface allow-list ∩ role grants.
Generation flows are admin-triggered and apply no role.

Only built-in tools are gated here. Tools from user-defined (custom) MCP servers
are outside the built-in universe and pass through for *open* surfaces (see
``OPEN_SURFACES`` / ``filter_surface_tools``); the *closed* chart-edit surface
emits its set verbatim instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from engine.builtin_mcp import builtin_tool_names


class AgentSurface(StrEnum):
    CHAT = "chat"
    CHART_EDIT = "chart_edit"
    DOC_GEN = "doc_gen"
    DASHBOARD_GEN = "dashboard_gen"
    TETHER_GEN = "tether_gen"


# The built-in tools each surface may invoke. This is the one place to manage
# per-surface tool access: add or remove a tool_name in a surface's list and both
# runtime enforcement and the admin surface-badge matrix follow. Every tool is
# spelled out per surface (no shared sub-lists) so each surface reads as a plain
# checklist of exactly what it can call. Tools not listed for a surface cannot be
# called there; a brand-new tdmcp tool is callable nowhere until added here.
SURFACE_TOOLS: dict[AgentSurface, frozenset[str]] = {
    # Main chat: read-only/analytical — every read tool, no write tools.
    AgentSurface.CHAT: frozenset(
        {
            # database
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            # codebases
            "list_codebases",
            "get_codebase_tree",
            "read_codebase_file",
            "search_codebase",
            # reports
            "list_reports",
            "get_report_data",
            # dashboards
            "list_dashboards",
            "get_dashboard_charts",
            # tethers
            "list_tethers",
            "get_tether_graph",
        }
    ),
    # Chart-edit panel: the DB reads it needs to reshape a chart's query, plus its
    # own write tool update_chart. Closed surface — emitted verbatim (see
    # management/consumers/chart_edit.py), not intersected with a role.
    AgentSurface.CHART_EDIT: frozenset(
        {
            # database
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            # write
            "update_chart",
        }
    ),
    # Doc generation: DB reads + codebase reads (code-grounded library docs explore
    # the selected codebases), plus its own write tool create_documentation.
    AgentSurface.DOC_GEN: frozenset(
        {
            # database
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            # codebases
            "list_codebases",
            "get_codebase_tree",
            "read_codebase_file",
            "search_codebase",
            # write
            "create_documentation",
        }
    ),
    # Dashboard/chart generation: DB reads + read existing dashboards/charts, plus
    # its own write tools create_dashboard and add_chart.
    AgentSurface.DASHBOARD_GEN: frozenset(
        {
            # database
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            # dashboards
            "list_dashboards",
            "get_dashboard_charts",
            # write
            "create_dashboard",
            "add_chart",
        }
    ),
    # Tether generation: DB reads + codebase reads (it bridges code ↔ schema), plus
    # its own write tool save_tether_graph.
    AgentSurface.TETHER_GEN: frozenset(
        {
            # database
            "list_databases",
            "list_tables",
            "get_table_schema",
            "query_database",
            "search_docs",
            # codebases
            "list_codebases",
            "get_codebase_tree",
            "read_codebase_file",
            "search_codebase",
            # write
            "save_tether_graph",
        }
    ),
}

# Surfaces that filter an externally-supplied candidate list (role grants / every
# enabled tool) and therefore let custom (non-built-in) MCP server tools pass
# through. CHART_EDIT is closed: it emits its own set verbatim and never a custom
# tool.
OPEN_SURFACES = frozenset(
    {
        AgentSurface.CHAT,
        AgentSurface.DOC_GEN,
        AgentSurface.DASHBOARD_GEN,
        AgentSurface.TETHER_GEN,
    }
)


def surface_tools(surface: AgentSurface) -> frozenset[str]:
    """The built-in tools a surface may invoke."""
    return SURFACE_TOOLS[surface]


def is_callable(
    surface: AgentSurface, tool_name: str, *, builtin_names: set[str] | None = None
) -> bool:
    """Whether ``tool_name`` may be invoked in ``surface``.

    Built-in tools are gated by the surface's allow-list. A non-built-in (custom
    MCP server) tool is callable only on *open* surfaces. Pass ``builtin_names``
    to avoid a repeated ``tdmcp`` introspection when checking many tools.
    """
    if builtin_names is None:
        builtin_names = builtin_tool_names()
    if tool_name in builtin_names:
        return tool_name in SURFACE_TOOLS[surface]
    return surface in OPEN_SURFACES


def callable_surfaces(
    tool_name: str, *, builtin_names: set[str] | None = None
) -> list[AgentSurface]:
    """The surfaces that may invoke ``tool_name`` — powers the admin badge matrix."""
    if builtin_names is None:
        builtin_names = builtin_tool_names()
    return [s for s in AgentSurface if is_callable(s, tool_name, builtin_names=builtin_names)]


def filter_surface_tools(surface: AgentSurface, names: Iterable[str]) -> list[str]:
    """Keep only the tools callable in ``surface``, preserving input order.

    Built-in tools outside the surface's allow-list are dropped; custom MCP
    server tools are kept (open surfaces). Use this on an *open* surface, which
    filters an externally-supplied candidate list (a role's grants, or every
    enabled tool). A *closed* surface should use ``surface_tools`` directly.
    """
    builtin_names = builtin_tool_names()
    return [n for n in names if is_callable(surface, n, builtin_names=builtin_names)]
