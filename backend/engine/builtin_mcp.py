"""Canonical definition of the built-in MCP server and its tools.

The real tools are served in-process by the `mcp` container (see
``mcp_server/tools/``). The DB rows below are the admin-facing mirror used by the
management (display, enable/disable) and by role-based access control
(``Role.allowed_tools``). They are seeded idempotently via a ``post_migrate``
hook (wired in ``engine/apps.py``) so a fresh install always has the built-in
server, and a deleted row self-heals on the next migrate.

Seeding is create-only: existing rows are never overwritten, so admin edits and
enable/disable toggles are preserved across deploys.
"""

from __future__ import annotations

BUILTIN_SERVER_NAME = "Built-in"
BUILTIN_SERVER_DESCRIPTION = (
    "Core database querying, documentation, dashboard, and tether tools that "
    "ship with TetherDust. Served in-process by the MCP container; always "
    "active and cannot be edited or deleted."
)

# (tool_name, display_name, category, description) — tool_name must match the
# function name registered in mcp_server/tools/__init__.py; category must match a
# value in ToolConfiguration.CATEGORY_CHOICES.
BUILTIN_TOOLS: list[tuple[str, str, str, str]] = [
    (
        "list_tables",
        "List Tables",
        "querying",
        "List all documented database tables, grouped by domain. Use first to "
        "discover what data exists.",
    ),
    (
        "get_table_schema",
        "Get Table Schema",
        "querying",
        "Get the full schema for a table: columns, data types, descriptions, "
        "enum/status mappings, and example values.",
    ),
    (
        "search_docs",
        "Search Docs",
        "docs",
        "Search documentation for data flows, business logic, table "
        "relationships, and architecture. Use for conceptual 'how does X work' "
        "questions rather than raw data.",
    ),
    (
        "get_query_examples",
        "Get Query Examples",
        "querying",
        "Return verified, working SQL examples for common use cases. Always call "
        "before writing a new query.",
    ),
    (
        "list_databases",
        "List Databases",
        "querying",
        "List configured database connections and their descriptions.",
    ),
    (
        "query_database",
        "Query Database",
        "querying",
        "Execute a read-only SELECT query and return results. Only SELECT is "
        "allowed; results are row-limited.",
    ),
    (
        "create_documentation",
        "Create Documentation",
        "docs",
        "Create or overwrite a documentation file. Becomes immediately searchable via search_docs.",
    ),
    (
        "create_dashboard",
        "Create Dashboard",
        "charts",
        "Create a new dashboard container, then add charts to it. Returns the "
        "dashboard_id used by add_chart.",
    ),
    (
        "add_chart",
        "Add Chart",
        "charts",
        "Add a d3.js chart to a dashboard. The chart's SQL runs against the "
        "chosen database and the d3 code renders the results.",
    ),
    (
        "update_chart",
        "Update Chart",
        "charts",
        "Update an existing chart's title, description, SQL query, or d3 code. "
        "Only the fields you pass are modified.",
    ),
    (
        "list_dashboards",
        "List Dashboards",
        "charts",
        "List dashboards available to the requesting user, including each "
        "dashboard's description and chart count.",
    ),
    (
        "get_dashboard_charts",
        "Get Dashboard Charts",
        "charts",
        "Return chart definitions for a dashboard, including chart metadata, "
        "key spec fields, and SQL queries.",
    ),
    (
        "list_reports",
        "List Reports",
        "reports",
        "List report definitions available to the requesting user, including "
        "database, schedule, latest run status, and row count.",
    ),
    (
        "get_report_data",
        "Get Report Data",
        "reports",
        "Run a report's stored read-only SQL query against its configured "
        "database and return live results as a markdown table.",
    ),
    (
        "save_tether_graph",
        "Save Tether Graph",
        "tethers",
        "Persist a tether graph (nodes, edges, summaries) to a version and "
        "promote it to the tether's current version.",
    ),
    (
        "list_tethers",
        "List Tethers",
        "tethers",
        "List Tethers available to the requesting user, including linked "
        "codebase, database source, and latest generated version status.",
    ),
    (
        "get_tether_graph",
        "Get Tether Graph",
        "tethers",
        "Return the current graph data for a Tether, summarizing code nodes, "
        "database nodes, and relationships.",
    ),
    (
        "list_codebases",
        "List Codebases",
        "codebases",
        "List the source-code repositories (codebases) available to the role. "
        "Use first to discover which codebases can be browsed.",
    ),
    (
        "get_codebase_tree",
        "Get Codebase Tree",
        "codebases",
        "List the files in a codebase, optionally scoped to a sub-directory. "
        "Use to find where code lives before reading files.",
    ),
    (
        "read_codebase_file",
        "Read Codebase File",
        "codebases",
        "Read the full contents of a single file from a codebase, fetched live "
        "from GitHub. Large files and binaries are refused.",
    ),
    (
        "search_codebase",
        "Search Codebase",
        "codebases",
        "Search code within a codebase by keyword via GitHub code search. Falls "
        "back to tree/file navigation when search is unavailable.",
    ),
]


def ensure_builtin_mcp(using: str | None = None) -> None:
    """Idempotently ensure the built-in MCP server and its tool rows exist.

    Create-only: never overwrites existing rows, so admin edits survive. Safe to
    call repeatedly (e.g. from post_migrate). Silently no-ops if the tables do
    not exist yet.
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

        for tool_name, display_name, category, description in BUILTIN_TOOLS:
            ToolConfiguration.objects.using(db).get_or_create(
                tool_name=tool_name,
                defaults={
                    "mcp_server": server,
                    "display_name": display_name,
                    "category": category,
                    "description": description,
                    "is_enabled": True,
                },
            )
    except (OperationalError, ProgrammingError):
        # Tables not migrated yet (e.g. mid-bootstrap). The next migrate run
        # will fire post_migrate again once the schema exists.
        pass
