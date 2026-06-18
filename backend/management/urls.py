"""URL patterns for the TetherDust custom admin panel."""

from django.urls import path

from .views import (
    agent,
    audit,
    auth,
    codebase,
    dashboard,
    database,
    docsource,
    home,
    mcp_server,
    report,
    role_user,
    tether,
    version,
)
from .views import settings as admin_settings

app_name = "management"

urlpatterns = [
    # Auth
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    # Overview
    path("", home.dashboard_view, name="dashboard"),
    path("quickstart/", home.quickstart_view, name="quickstart"),
    path("quickstart/finish/", home.quickstart_finish_view, name="quickstart_finish"),
    path("version/", version.version_view, name="version"),
    # Database Connections
    path("databases/", database.database_list_view, name="database_list"),
    path("databases/add/", database.database_engine_picker_view, name="database_add"),
    path("databases/add/<str:engine>/", database.database_form_view, name="database_add_engine"),
    path("databases/<str:pk>/edit/", database.database_form_view, name="database_edit"),
    path("databases/<str:pk>/delete/", database.database_delete_view, name="database_delete"),
    path("databases/<str:pk>/test/", database.database_test_view, name="database_test"),
    # Codebases
    path("codebases/", codebase.codebase_list_view, name="codebase_list"),
    path("codebases/add/", codebase.codebase_provider_picker_view, name="codebase_add"),
    path(
        "codebases/add/<str:provider>/", codebase.codebase_form_view, name="codebase_add_provider"
    ),
    path("codebases/<str:pk>/edit/", codebase.codebase_form_view, name="codebase_edit"),
    path("codebases/<str:pk>/delete/", codebase.codebase_delete_view, name="codebase_delete"),
    path("codebases/<str:pk>/sync/", codebase.codebase_sync_view, name="codebase_sync"),
    path("codebases/<str:pk>/status/", codebase.codebase_status_view, name="codebase_status"),
    # Documentation Sources
    path("docsources/", docsource.docsource_list_view, name="docsource_list"),
    path(
        "docsources/add/create-with-ai/",
        docsource.docsource_generate_page_view,
        name="docsource_generate_page",
    ),
    path(
        "docsources/add/create-library/",
        docsource.docsource_library_page_view,
        name="docsource_library_page",
    ),
    path("docsources/add/", docsource.docsource_add_picker_view, name="docsource_add"),
    path("docsources/add/register/", docsource.docsource_form_view, name="docsource_register"),
    path("docsources/<str:pk>/edit/", docsource.docsource_form_view, name="docsource_edit"),
    path("docsources/<str:pk>/delete/", docsource.docsource_delete_view, name="docsource_delete"),
    path(
        "docsources/<str:pk>/validate/",
        docsource.docsource_validate_view,
        name="docsource_validate",
    ),
    path("docsources/generate/", docsource.docsource_generate_view, name="docsource_generate"),
    path(
        "docsources/generate-library/",
        docsource.docsource_generate_library_view,
        name="docsource_generate_library",
    ),
    path(
        "docsources/generate/<str:pk>/status/",
        docsource.docsource_generate_status_view,
        name="docsource_generate_status",
    ),
    # Agent Configurations
    path("agents/", agent.agent_list_view, name="agent_list"),
    path("agents/add/", agent.agent_type_picker_view, name="agent_add"),
    path("agents/add/<str:agent_type>/", agent.agent_form_view, name="agent_add_type"),
    path("agents/<str:pk>/edit/", agent.agent_form_view, name="agent_edit"),
    path("agents/<str:pk>/delete/", agent.agent_delete_view, name="agent_delete"),
    path("agents/<str:pk>/activate/", agent.agent_activate_view, name="agent_activate"),
    path(
        "agents/<str:pk>/device-login/start/",
        agent.agent_device_login_start,
        name="agent_device_login_start",
    ),
    path(
        "agents/<str:pk>/device-login/status/<str:login_id>/",
        agent.agent_device_login_status,
        name="agent_device_login_status",
    ),
    # MCP Servers
    path("mcp-servers/", mcp_server.mcp_server_list_view, name="mcp_server_list"),
    path("mcp-servers/add/", mcp_server.mcp_server_form_view, name="mcp_server_add"),
    path("mcp-servers/<str:pk>/", mcp_server.mcp_server_detail_view, name="mcp_server_detail"),
    path("mcp-servers/<str:pk>/edit/", mcp_server.mcp_server_form_view, name="mcp_server_edit"),
    path(
        "mcp-servers/<str:pk>/delete/", mcp_server.mcp_server_delete_view, name="mcp_server_delete"
    ),
    path("mcp-servers/<str:pk>/test/", mcp_server.mcp_server_test_view, name="mcp_server_test"),
    # Tools (nested under MCP Servers) — read-only view
    path(
        "mcp-servers/<str:server_pk>/tools/<str:pk>/",
        mcp_server.tool_detail_view,
        name="tool_detail",
    ),
    # Prompts (nested under MCP Servers)
    path(
        "mcp-servers/<str:server_pk>/prompts/add/", mcp_server.prompt_form_view, name="prompt_add"
    ),
    path(
        "mcp-servers/<str:server_pk>/prompts/<str:pk>/edit/",
        mcp_server.prompt_form_view,
        name="prompt_edit",
    ),
    path(
        "mcp-servers/<str:server_pk>/prompts/<str:pk>/toggle/",
        mcp_server.prompt_toggle_view,
        name="prompt_toggle",
    ),
    path(
        "mcp-servers/<str:server_pk>/prompts/<str:pk>/delete/",
        mcp_server.prompt_delete_view,
        name="prompt_delete",
    ),
    # Roles & Permissions
    path("roles/", role_user.role_list_view, name="role_list"),
    path("roles/add/", role_user.role_form_view, name="role_add"),
    path("roles/<str:pk>/edit/", role_user.role_form_view, name="role_edit"),
    path("roles/<str:pk>/delete/", role_user.role_delete_view, name="role_delete"),
    # User Management
    path("users/", role_user.user_list_view, name="user_list"),
    path("users/add/", role_user.user_create_view, name="user_add"),
    path("users/<str:pk>/edit/", role_user.user_edit_view, name="user_edit"),
    path("users/<str:pk>/delete/", role_user.user_delete_view, name="user_delete"),
    # Settings
    path("settings/", admin_settings.general_settings_view, name="settings"),
    path("settings/email/", admin_settings.smtp_settings_view, name="settings_email"),
    path("settings/email/test/", admin_settings.smtp_test_view, name="smtp_test"),
    # Dashboards
    path("dashboards/", dashboard.dashboard_list_view_admin, name="dashboard_list"),
    path("dashboards/add/", dashboard.dashboard_form_view_admin, name="dashboard_add"),
    path(
        "dashboards/create-with-ai/",
        dashboard.dashboard_generate_page_view,
        name="dashboard_generate_page",
    ),
    path("dashboards/<str:pk>/", dashboard.dashboard_detail_view_admin, name="dashboard_detail"),
    path("dashboards/<str:pk>/edit/", dashboard.dashboard_form_view_admin, name="dashboard_edit"),
    path(
        "dashboards/<str:pk>/delete/",
        dashboard.dashboard_delete_view_admin,
        name="dashboard_delete",
    ),
    path("dashboards/generate/", dashboard.dashboard_generate_view, name="dashboard_generate"),
    path(
        "dashboards/generate/<str:pk>/status/",
        dashboard.dashboard_generate_status_view,
        name="dashboard_generate_status",
    ),
    path("dashboards/<str:dashboard_pk>/charts/add/", dashboard.chart_form_view, name="chart_add"),
    path(
        "dashboards/<str:dashboard_pk>/charts/<str:pk>/edit/",
        dashboard.chart_form_view,
        name="chart_edit",
    ),
    path(
        "dashboards/<str:dashboard_pk>/charts/<str:pk>/delete/",
        dashboard.chart_delete_view,
        name="chart_delete",
    ),
    path(
        "dashboards/<str:dashboard_pk>/charts/preview/",
        dashboard.chart_preview_view,
        name="chart_preview",
    ),
    path(
        "dashboards/<str:dashboard_pk>/charts/<str:pk>/state/",
        dashboard.chart_state_view,
        name="chart_state",
    ),
    path("dashboards/charts/<str:pk>/data/", dashboard.chart_data_view, name="chart_data"),
    # Reports
    path("reports/", report.report_list_view, name="report_list"),
    path("reports/add/", report.report_form_view, name="report_add"),
    path("reports/<str:pk>/edit/", report.report_form_view, name="report_edit"),
    path("reports/<str:pk>/delete/", report.report_delete_view, name="report_delete"),
    path("reports/<str:pk>/run/", report.report_run_view, name="report_run"),
    path("reports/<str:pk>/preview/", report.report_preview_view, name="report_preview"),
    path("reports/<str:pk>/toggle/", report.report_toggle_view, name="report_toggle"),
    # Report Executions (Monitoring)
    path("report-runs/", report.report_execution_list_view, name="report_execution_list"),
    path(
        "report-runs/<str:pk>/", report.report_execution_detail_view, name="report_execution_detail"
    ),
    # Tethers
    path("tethers/", tether.tether_list_view, name="tether_list"),
    path("tethers/add/", tether.tether_form_view, name="tether_add"),
    path("tethers/<str:pk>/", tether.tether_detail_view, name="tether_detail"),
    path("tethers/<str:pk>/edit/", tether.tether_form_view, name="tether_edit"),
    path("tethers/<str:pk>/delete/", tether.tether_delete_view, name="tether_delete"),
    path("tethers/<str:pk>/regenerate/", tether.tether_regenerate_view, name="tether_regenerate"),
    path("tethers/<str:pk>/status/", tether.tether_status_view, name="tether_status"),
    path(
        "tethers/<str:pk>/versions/<str:version_pk>/",
        tether.tether_version_detail_view,
        name="tether_version_detail",
    ),
    # Audit Logs
    path("audit/", audit.audit_list_view, name="audit_list"),
    # Doc Generation Logs
    path("docgen-logs/", audit.docgen_log_list_view, name="docgen_log_list"),
    path("docgen-logs/<str:pk>/", audit.docgen_log_detail_view, name="docgen_log_detail"),
    # Chart Generation Logs
    path("chartgen-logs/", audit.chartgen_log_list_view, name="chartgen_log_list"),
    path("chartgen-logs/<str:pk>/", audit.chartgen_log_detail_view, name="chartgen_log_detail"),
    # Chat Sessions
    path("sessions/", audit.session_list_view, name="session_list"),
    path("sessions/<str:pk>/", audit.session_detail_view, name="session_detail"),
]
