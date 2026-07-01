"""Internal service API routes, mounted at /api/internal/."""

from django.urls import path

from .views import (
    ChartCreateView,
    ChartUpdateView,
    DashboardCreateView,
    QueryAuditCreateView,
    TetherGraphSaveView,
)

urlpatterns = [
    path("query-audit/", QueryAuditCreateView.as_view(), name="internal-query-audit"),
    path("dashboards/", DashboardCreateView.as_view(), name="internal-dashboard-create"),
    path(
        "dashboards/<str:dashboard_id>/charts/",
        ChartCreateView.as_view(),
        name="internal-chart-create",
    ),
    path("charts/<str:chart_id>/", ChartUpdateView.as_view(), name="internal-chart-update"),
    path(
        "tether-versions/<str:version_id>/graph/",
        TetherGraphSaveView.as_view(),
        name="internal-tether-graph",
    ),
]
