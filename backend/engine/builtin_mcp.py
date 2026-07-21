"""Canonical definition of the built-in MCP server and its tools.

The real tools are served in-process by the `tdmcp` container (see
``tdmcp/tools/``). Each tool's ``tool_name``, ``display_name``, and
``description`` below are derived directly from the tool's own function name
and docstring — the exact values FastMCP exposes to the agent — instead of a
hand-maintained copy that can silently drift from the real implementation (or
even go missing entirely if a new tool is added to tdmcp but never mirrored
here).

``category`` has no equivalent in tdmcp — it's a TetherDust admin-UI grouping
concept, not part of the MCP tool itself — so it's the one piece of metadata
below that still needs a small manual mapping. A tool absent from it still
gets seeded; it just falls back to category "" ("Other", see
``ToolConfiguration.CATEGORY_CHOICES``).

The DB rows are the admin-facing mirror used by the management (display,
enable/disable) and by role-based access control (``Role.allowed_tools``).
They're (re)synced idempotently via a ``post_migrate`` hook (wired in
``engine/apps.py``) so a fresh install always has the built-in server, a
deleted row self-heals on the next migrate, and edits to a tdmcp tool's
docstring show up on the next deploy without a data migration.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

BUILTIN_SERVER_NAME = "Built-in"
BUILTIN_SERVER_DESCRIPTION = (
    "Core database querying, documentation, dashboard, and tether tools that ship with TetherDust."
)

# tool_name -> ToolConfiguration category (must match a value in
# ToolConfiguration.CATEGORY_CHOICES).
TOOL_CATEGORIES: dict[str, str] = {
    "list_tables": "querying",
    "get_table_schema": "querying",
    "list_databases": "querying",
    "query_database": "querying",
    "search_docs": "docs",
    "create_documentation": "docs",
    "create_dashboard": "charts",
    "add_chart": "charts",
    "update_chart": "charts",
    "list_dashboards": "charts",
    "get_dashboard_charts": "charts",
    "list_reports": "reports",
    "get_report_data": "reports",
    "save_tether_graph": "tethers",
    "list_tethers": "tethers",
    "get_tether_graph": "tethers",
    "list_codebases": "codebases",
    "get_codebase_tree": "codebases",
    "read_codebase_file": "codebases",
    "search_codebase": "codebases",
}


def _display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _summary(handler: Callable[..., object]) -> str:
    """The first paragraph of the tool's docstring.

    This is the same text FastMCP sends the agent as the tool's description,
    minus any detailed usage notes (REQUIREMENTS, examples, ...) that follow
    the summary paragraph — those are written for the agent, not for an admin
    skimming a tool list.
    """
    doc = inspect.getdoc(handler) or ""
    return doc.split("\n\n", 1)[0].strip()


def iter_builtin_tools() -> list[tuple[str, str, str, str]]:
    """(tool_name, display_name, category, description) for every real tool,
    read live from ``tdmcp.tools`` instead of a hardcoded duplicate."""
    from tdmcp.tools import iter_tool_handlers

    return [
        (
            handler.__name__,
            _display_name(handler.__name__),
            TOOL_CATEGORIES.get(handler.__name__, ""),
            _summary(handler),
        )
        for handler in iter_tool_handlers()
    ]


def describe_builtin_tool_schemas() -> dict[str, dict[str, object]]:
    """tool_name -> {parameters, returns} for every real built-in tool.

    Read live from ``tdmcp`` (``describe_tool_schema``, built via FastMCP's own
    ``Tool.from_function``) rather than persisted, since it's cheap to
    recompute and there's nothing admin-editable about a tool's real
    signature to preserve across requests.
    """
    from tdmcp.tools import describe_tool_schema, iter_tool_handlers

    return {handler.__name__: describe_tool_schema(handler) for handler in iter_tool_handlers()}


def ensure_builtin_mcp(using: str | None = None) -> None:
    """Idempotently ensure the built-in MCP server and its tool rows exist and
    match the real tools' current name/category/description.

    Safe to call repeatedly (e.g. from post_migrate). Silently no-ops if the
    tables do not exist yet (e.g. mid-bootstrap) — the next migrate run fires
    post_migrate again once the schema exists. ``is_enabled`` is only ever set
    on first create, never on re-sync, since it's the one field an operator
    can actually flip.

    Also deletes any built-in tool row whose tool_name is no longer in
    ``iter_builtin_tools()`` (i.e. the tool was removed from tdmcp). This is
    safe because the built-in server's tools have no admin-editable fields to
    lose — the admin UI is read-only for them — so a stale row is pure
    leftover, not a discarded edit.
    """
    from django.db import DEFAULT_DB_ALIAS
    from django.db.utils import OperationalError, ProgrammingError

    from .models import MCPServerConfiguration, ToolConfiguration

    db = using or DEFAULT_DB_ALIAS
    manager = MCPServerConfiguration.objects.using(db)

    try:
        server = manager.filter(is_builtin=True).first()
        if server is None:
            server = manager.create(
                name=BUILTIN_SERVER_NAME,
                description=BUILTIN_SERVER_DESCRIPTION,
                url="",
                transport="",
                is_active=True,
                is_builtin=True,
            )

        current_tools = iter_builtin_tools()
        for tool_name, display_name, category, description in current_tools:
            ToolConfiguration.objects.using(db).update_or_create(
                tool_name=tool_name,
                defaults={
                    "mcp_server": server,
                    "display_name": display_name,
                    "category": category,
                    "description": description,
                },
            )

        current_tool_names = {tool_name for tool_name, *_ in current_tools}
        ToolConfiguration.objects.using(db).filter(mcp_server=server).exclude(
            tool_name__in=current_tool_names
        ).delete()
    except (OperationalError, ProgrammingError):
        # Tables not migrated yet (e.g. mid-bootstrap). The next migrate run
        # will fire post_migrate again once the schema exists.
        pass
