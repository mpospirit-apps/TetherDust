"""URL routes for v1 of the SPA-facing API (mounted at /api/v1/)."""

from django.urls import include, path

from .agent_status import AgentStatusView
from .auth import CsrfView, LoginView, LogoutView, MeView
from .chat import ChatSessionDetailView, ChatSessionsView, DocSourcesView, PromptsView
from .dashboards import ChartDataView, DashboardDetailView, DashboardsView
from .docs import DocsContentView, DocsSourcesView
from .reports import (
    ExecutionDetailView,
    ExecutionDownloadView,
    ExecutionEmailView,
    ReportHistoryView,
    ReportLatestView,
    ReportsView,
)
from .tethers import TetherDetailView, TetherGraphView, TethersView

app_name = "api_v1"

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("agent-status/", AgentStatusView.as_view(), name="agent-status"),
    path("chat/sessions/", ChatSessionsView.as_view(), name="chat-sessions"),
    path(
        "chat/sessions/<str:session_id>/",
        ChatSessionDetailView.as_view(),
        name="chat-session-detail",
    ),
    path("chat/doc-sources/", DocSourcesView.as_view(), name="chat-doc-sources"),
    path("chat/prompts/", PromptsView.as_view(), name="chat-prompts"),
    path("docs/sources/", DocsSourcesView.as_view(), name="docs-sources"),
    path("docs/content/", DocsContentView.as_view(), name="docs-content"),
    path("dashboards/", DashboardsView.as_view(), name="dashboards"),
    path("dashboards/<str:pk>/", DashboardDetailView.as_view(), name="dashboard-detail"),
    path("charts/<str:pk>/data/", ChartDataView.as_view(), name="chart-data"),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("reports/<str:pk>/latest/", ReportLatestView.as_view(), name="report-latest"),
    path("reports/<str:pk>/history/", ReportHistoryView.as_view(), name="report-history"),
    path("executions/<str:pk>/", ExecutionDetailView.as_view(), name="execution-detail"),
    path(
        "executions/<str:pk>/download/<str:fmt>/",
        ExecutionDownloadView.as_view(),
        name="execution-download",
    ),
    path(
        "executions/<str:pk>/send-email/",
        ExecutionEmailView.as_view(),
        name="execution-email",
    ),
    path("tethers/", TethersView.as_view(), name="tethers"),
    path("tethers/<str:pk>/", TetherDetailView.as_view(), name="tether-detail"),
    path("tethers/<str:pk>/graph/", TetherGraphView.as_view(), name="tether-graph"),
    # Staff admin console (F1+).
    path("admin/", include("api.v1.admin.urls")),
]
