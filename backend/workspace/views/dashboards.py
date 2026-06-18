"""User-facing dashboard views and chart data API."""

import datetime
import decimal
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.decorators import login_required
from engine.services import PermissionService, get

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


def _serialize_sql_value(val: object) -> object:
    """Convert non-JSON-serializable SQL result values."""
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, datetime.timedelta):
        return val.total_seconds()
    return val


@login_required(login_url="/login/")
def dashboards_view(request: HttpRequest) -> HttpResponse:
    """Dashboard list — role-filtered."""
    from engine.models import Dashboard

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        dashboards = (
            Dashboard.objects.filter(is_active=True)
            .annotate(chart_count=Count("charts"))
            .order_by("name")
        )
    else:
        profile = getattr(user, "profile", None)
        if not profile or not get(PermissionService).can_view_dashboards(profile):
            return render(
                request,
                "workspace/dashboards.html",
                {
                    "dashboards": [],
                    "all_dashboards": [],
                    "has_access": False,
                },
            )
        dashboards = (
            get(PermissionService)
            .get_allowed_dashboards(profile)
            .annotate(chart_count=Count("charts"))
            .order_by("name")
        )

    return render(
        request,
        "workspace/dashboards.html",
        {
            "dashboards": dashboards,
            "all_dashboards": dashboards,
            "current_dashboard_id": None,
            "has_access": True,
        },
    )


@login_required(login_url="/login/")
def dashboard_detail_view_user(request: HttpRequest, pk: str) -> HttpResponse:
    """Dashboard detail with d3.js chart rendering — role-checked."""
    from engine.models import Dashboard

    dashboard = get_object_or_404(Dashboard, pk=pk, is_active=True)
    user = cast("AbstractUser", request.user)

    if user.is_staff:
        all_dashboards = Dashboard.objects.filter(is_active=True).order_by("name")
    else:
        profile = getattr(user, "profile", None)
        if not profile or not get(PermissionService).can_view_dashboards(profile):
            return redirect("workspace:dashboards")
        if not get(PermissionService).get_allowed_dashboards(profile).filter(pk=pk).exists():
            return redirect("workspace:dashboards")
        all_dashboards = get(PermissionService).get_allowed_dashboards(profile).order_by("name")

    charts = cast(Any, dashboard).charts.filter(is_active=True).select_related("database")

    return render(
        request,
        "workspace/dashboard_detail.html",
        {
            "dashboard": dashboard,
            "charts": charts,
            "all_dashboards": all_dashboards,
            "current_dashboard_id": dashboard.pk,
            "has_access": True,
        },
    )


@login_required(login_url="/login/")
def chart_data_api_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Chart data API for user-facing dashboards. Role-checked."""
    from engine.engines.db_runner import run_query
    from engine.models import Chart

    chart = get_object_or_404(Chart.objects.select_related("database", "dashboard"), pk=pk)
    force_refresh = request.GET.get("refresh") == "1"

    req_user = cast("AbstractUser", request.user)
    if not req_user.is_staff:
        profile = getattr(req_user, "profile", None)
        if (
            not profile
            or not get(PermissionService)
            .get_allowed_dashboards(profile)
            .filter(pk=chart.dashboard_id)
            .exists()
        ):
            return JsonResponse({"error": "Access denied"}, status=403)

    if not force_refresh and chart.cached_data and chart.cached_data.get("rows"):
        return JsonResponse(
            {
                "columns": chart.cached_data.get("columns", []),
                "data": chart.cached_data.get("rows", []),
                "cached": True,
                "refreshed_at": chart.cached_data.get("refreshed_at"),
            }
        )

    try:
        db_conn = chart.database
        columns, raw_rows = run_query(db_conn, chart.sql_query)
        rows = [{col: _serialize_sql_value(v) for col, v in zip(columns, row)} for row in raw_rows]

        now_str = timezone.now().isoformat()
        chart.cached_data = {
            "columns": columns,
            "rows": rows,
            "refreshed_at": now_str,
        }
        chart.last_refreshed_at = timezone.now()
        chart.last_error = ""
        chart.save(update_fields=["cached_data", "last_refreshed_at", "last_error"])

        return JsonResponse(
            {
                "columns": columns,
                "data": rows,
                "cached": False,
                "refreshed_at": now_str,
            }
        )
    except Exception as e:
        chart.last_error = str(e)
        chart.save(update_fields=["last_error"])
        return JsonResponse({"error": str(e)}, status=500)
