"""Public dashboards API — role-scoped list/detail + chart data.

Replaces ``workspace/views/dashboards.py``. Charts ship their stored
``custom_d3_code`` so the SPA can execute it client-side (the existing
``new Function`` rendering, preserved). Chart data is cached/served via
``engine.engines.charts.chart_data``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Count
from engine.engines.charts import chart_data
from engine.models import Chart, Dashboard
from engine.services import PermissionService, get
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewDashboards

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db.models import QuerySet


def _visible_dashboards(user: AbstractUser) -> QuerySet[Dashboard]:
    """Active dashboards the user may see (staff → all; else role-allowed)."""
    if user.is_staff:
        return Dashboard.objects.filter(is_active=True)
    profile = getattr(user, "profile", None)
    if not profile or not get(PermissionService).can_view_dashboards(profile):
        return Dashboard.objects.none()
    return get(PermissionService).get_allowed_dashboards(profile)


def _chart_dict(chart: Chart) -> dict[str, Any]:
    return {
        "id": chart.pk,
        "title": chart.title,
        "description": chart.description,
        "chart_type": chart.chart_type,
        "custom_d3_code": chart.custom_d3_code,
        "width": chart.width,
        "height": chart.height,
        "position": chart.position,
        "last_refreshed_at": (
            chart.last_refreshed_at.isoformat() if chart.last_refreshed_at else None
        ),
    }


class DashboardsView(APIView):
    """Role-scoped dashboard list (with chart counts)."""

    permission_classes = [CanViewDashboards]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        dashboards = (
            _visible_dashboards(user).annotate(chart_count=Count("charts")).order_by("name")
        )
        return Response(
            {
                "dashboards": [
                    {
                        "id": d.pk,
                        "name": d.name,
                        "description": d.description,
                        "chart_count": getattr(d, "chart_count", 0),
                        "auto_refresh": d.auto_refresh,
                        "refresh_interval": d.refresh_interval,
                    }
                    for d in dashboards
                ]
            }
        )


class DashboardDetailView(APIView):
    """A single dashboard with its active charts (role-checked)."""

    permission_classes = [CanViewDashboards]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        dashboard = _visible_dashboards(user).filter(pk=pk, is_active=True).first()
        if dashboard is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        charts = (
            Chart.objects.filter(dashboard=dashboard, is_active=True)
            .select_related("database")
            .order_by("position", "title")
        )
        return Response(
            {
                "id": dashboard.pk,
                "name": dashboard.name,
                "description": dashboard.description,
                "auto_refresh": dashboard.auto_refresh,
                "refresh_interval": dashboard.refresh_interval,
                "charts": [_chart_dict(c) for c in charts],
            }
        )


class ChartDataView(APIView):
    """Chart data (cached unless ``?refresh=1``), role-checked via its dashboard."""

    permission_classes = [CanViewDashboards]

    def get(self, request: Request, pk: str) -> Response:
        chart = Chart.objects.select_related("database", "dashboard").filter(pk=pk).first()
        if chart is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        user = cast("AbstractUser", request.user)
        if not user.is_staff:
            profile = getattr(user, "profile", None)
            allowed = (
                profile
                and get(PermissionService)
                .get_allowed_dashboards(profile)
                .filter(pk=chart.dashboard_id)
                .exists()
            )
            if not allowed:
                return Response({"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        force_refresh = request.query_params.get("refresh") == "1"
        try:
            return Response(chart_data(chart, force_refresh))
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
