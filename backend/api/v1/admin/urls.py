"""Admin (staff) API routes, mounted at /api/v1/admin/."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .agents import AgentViewSet
from .audit import AuditLogDetailView, AuditLogView, SessionDetailView, SessionsView
from .codebases import CodebaseViewSet
from .dashboards import (
    ChartGenerationLogViewSet,
    ChartViewSet,
    DashboardViewSet,
)
from .databases import DatabaseConnectionViewSet
from .docsources import DocGenerationLogViewSet, DocSourceViewSet
from .mcp_servers import MCPServerViewSet, PromptViewSet
from .overview import OverviewView
from .reports import ReportDefinitionViewSet, ReportExecutionViewSet
from .roles import RoleViewSet
from .settings import GeneralSettingsView, SmtpSettingsView, SmtpTestView
from .tethers import TetherViewSet
from .users import UserViewSet
from .version import VersionView

router = DefaultRouter()
router.register("agents", AgentViewSet, basename="admin-agent")
router.register("charts", ChartViewSet, basename="admin-chart")
router.register("chartgen-logs", ChartGenerationLogViewSet, basename="admin-chartgen-log")
router.register("codebases", CodebaseViewSet, basename="admin-codebase")
router.register("dashboards", DashboardViewSet, basename="admin-dashboard")
router.register("databases", DatabaseConnectionViewSet, basename="admin-database")
router.register("docsources", DocSourceViewSet, basename="admin-docsource")
router.register("docgen-logs", DocGenerationLogViewSet, basename="admin-docgen-log")
router.register("mcp-servers", MCPServerViewSet, basename="admin-mcp-server")
router.register("mcp-prompts", PromptViewSet, basename="admin-mcp-prompt")
router.register("reports", ReportDefinitionViewSet, basename="admin-report")
router.register("report-executions", ReportExecutionViewSet, basename="admin-report-execution")
router.register("roles", RoleViewSet, basename="admin-role")
router.register("tethers", TetherViewSet, basename="admin-tether")
router.register("users", UserViewSet, basename="admin-user")

urlpatterns = [
    *router.urls,
    path("overview/", OverviewView.as_view(), name="admin-overview"),
    path("version/", VersionView.as_view(), name="admin-version"),
    path("settings/general/", GeneralSettingsView.as_view(), name="admin-settings-general"),
    path("settings/smtp/", SmtpSettingsView.as_view(), name="admin-settings-smtp"),
    path("settings/smtp/test/", SmtpTestView.as_view(), name="admin-settings-smtp-test"),
    path("audit/", AuditLogView.as_view(), name="admin-audit"),
    path("audit/<str:audit_id>/", AuditLogDetailView.as_view(), name="admin-audit-detail"),
    path("sessions/", SessionsView.as_view(), name="admin-sessions"),
    path("sessions/<str:session_id>/", SessionDetailView.as_view(), name="admin-session-detail"),
]
