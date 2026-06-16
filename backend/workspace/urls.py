from django.urls import path

from . import views

app_name = "workspace"

urlpatterns = [
    path("", views.login_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("chat/", views.chat_view, name="chat"),
    path("chat/sessions/", views.sessions_list_view, name="sessions_list"),
    path("chat/doc-sources/", views.doc_sources_api_view, name="doc_sources_api"),
    path("chat/prompts/", views.prompts_api_view, name="prompts_api"),
    path("chat/sessions/<int:session_id>/", views.session_delete_view, name="session_delete"),
    path("docs/", views.docs_view, name="docs"),
    path("docs/<int:source_id>/<path:file_path>", views.docs_content_view, name="docs_content"),
    path("reports/", views.reports_view, name="reports"),
    path("reports/<int:definition_id>/latest/", views.report_latest_view, name="report_latest"),
    path("reports/<int:definition_id>/history/", views.report_history_view, name="report_history"),
    path(
        "reports/execution/<int:execution_id>/",
        views.report_execution_content_view,
        name="report_execution_content",
    ),
    path(
        "reports/execution/<int:execution_id>/download/<str:fmt>/",
        views.report_download_view,
        name="report_download",
    ),
    path(
        "reports/execution/<int:execution_id>/send-email/",
        views.report_send_email_view,
        name="report_send_email",
    ),
    path("dashboards/", views.dashboards_view, name="dashboards"),
    path("dashboards/<int:pk>/", views.dashboard_detail_view_user, name="dashboard_detail"),
    path("dashboards/charts/<int:pk>/data/", views.chart_data_api_view, name="chart_data_api"),
    path("tethers/", views.tethers_list_view, name="tethers"),
    path("tethers/<int:pk>/", views.tether_view, name="tether_detail"),
    path("tethers/<int:pk>/graph.json", views.tether_graph_json_view, name="tether_graph_json"),
    path("healthz", views.healthz_view, name="healthz"),
    path("readyz", views.readyz_view, name="readyz"),
    path("agent-status/", views.agent_status_view, name="agent_status"),
]
