"""Per-request context variables for the MCP server.

These are set by the token-based filter registry in server.py (Streamable HTTP mode)
and read by tool modules to enforce access controls. Separated into their own module
to avoid circular imports between server.py and tool modules.
"""

import contextvars

# Per-request allowed tools — read by server.py list_tools/call_tool handlers.
request_allowed_tools: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_tools", default=None
)

# Per-request allowed databases — read by tools/_db_shared.py.
request_allowed_databases: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_databases", default=None
)

# Per-request allowed documentation sources — read by tools/_db_shared.py.
request_allowed_doc_sources: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_doc_sources", default=None
)

# Per-request allowed codebases — read by tools/_codebase_shared.py.
request_allowed_codebases: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_codebases", default=None
)

# Per-request allowed reports — read by tools/list_reports.py and get_report_data.py.
# Contains report names (unique field). None means unrestricted.
request_allowed_reports: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_reports", default=None
)

# Per-request allowed dashboards — read by tools/list_dashboards.py and get_dashboard_charts.py.
# Contains dashboard names (unique field). None means unrestricted.
request_allowed_dashboards: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_dashboards", default=None
)

# Per-request allowed tethers — read by tools/list_tethers.py and get_tether_graph.py.
# Contains tether IDs as strings (names are not unique). None means unrestricted.
request_allowed_tethers: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "request_allowed_tethers", default=None
)

# Per-request max row limit — read by tools/_db_shared.py.
request_max_row_limit: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "request_max_row_limit", default=None
)

# Per-request filter token — set by server.py handle_mcp, read by call_tool so
# tool-call tracking is scoped per request instead of a single global buffer.
request_filter_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_filter_token", default=None
)

# Per-request user id — the Django user whose chat turn spawned this request.
# Threaded through the filter token so tools/query_database.py can attribute the
# audit-log entry to a user. None in unauthenticated (stdio dev) use.
request_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "request_user_id", default=None
)

# Per-request chat session id — carried alongside request_user_id for audit
# context. None when no token is registered.
request_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_session_id", default=None
)
