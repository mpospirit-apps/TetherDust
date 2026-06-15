"""User-facing views for the chat app.

Split into six domain modules; this package re-exports the public callables
referenced by `chat/urls.py` so existing `views.<name>` paths keep working.
"""

from .api import (
    agent_status_view,
    doc_sources_api_view,
    healthz_view,
    login_view,
    logout_view,
    prompts_api_view,
    readyz_view,
)
from .chat import (
    chat_view,
    session_delete_view,
    sessions_list_view,
)
from .dashboards import (
    chart_data_api_view,
    dashboard_detail_view_user,
    dashboards_view,
)
from .docs import (
    docs_content_view,
    docs_view,
)
from .reports import (
    report_download_view,
    report_execution_content_view,
    report_history_view,
    report_latest_view,
    report_send_email_view,
    reports_view,
)
from .tethers import (
    tether_graph_json_view,
    tether_view,
    tethers_list_view,
)

__all__ = [
    "agent_status_view",
    "chart_data_api_view",
    "chat_view",
    "dashboard_detail_view_user",
    "dashboards_view",
    "doc_sources_api_view",
    "docs_content_view",
    "docs_view",
    "healthz_view",
    "login_view",
    "logout_view",
    "prompts_api_view",
    "readyz_view",
    "report_download_view",
    "report_execution_content_view",
    "report_history_view",
    "report_latest_view",
    "report_send_email_view",
    "reports_view",
    "session_delete_view",
    "sessions_list_view",
    "tether_graph_json_view",
    "tether_view",
    "tethers_list_view",
]
