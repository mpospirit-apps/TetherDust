"""User-facing report views: viewer page, latest/history HTMX endpoints, downloads, email."""

import csv
import io
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.decorators import login_required

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods


@login_required
@ensure_csrf_cookie
def reports_view(request: HttpRequest) -> HttpResponse:
    """Reports viewer — sidebar listing + content area."""
    from engine.models import ReportDefinition

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        reports = ReportDefinition.objects.filter(is_active=True).select_related("database")
    else:
        profile = getattr(user, "profile", None)
        if not profile or not profile.can_view_reports:
            return render(request, "workspace/reports.html", {"reports": [], "has_access": False})
        reports = profile.get_allowed_reports().select_related("database")

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    def _report_group(dt: datetime | None) -> str:
        if dt is None:
            return "Never Run"
        if dt >= today_start:
            return "Today"
        elif dt >= yesterday_start:
            return "Yesterday"
        else:
            day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            days_ago = (today_start - day_start).days
            if days_ago <= 7:
                return dt.strftime("%A")
            else:
                return dt.strftime("%B %Y")

    report_list = []
    for report in reports:
        latest = report.get_latest_execution()
        group = _report_group(latest.started_at if latest else None)
        report_list.append(
            {
                "id": report.pk,
                "name": report.name,
                "description": report.description,
                "database": report.database.name,
                "latest_exec": latest,
                "group": group,
            }
        )

    group_order = []
    groups_map: dict[str, list[dict[str, object]]] = {}
    for r in report_list:
        g = cast(str, r["group"])
        if g not in groups_map:
            groups_map[g] = []
            group_order.append(g)
        groups_map[g].append(r)

    def _group_sort_key(label: str) -> tuple[int | str, ...]:
        if label == "Today":
            return (0,)
        if label == "Yesterday":
            return (1,)
        if label == "Never Run":
            return (999,)
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if label in weekdays:
            return (2, weekdays.index(label))
        try:
            d = datetime.strptime(label, "%B %Y")
            return (3, -d.year, -d.month)
        except ValueError:
            return (4, label)

    sorted_groups = sorted(group_order, key=_group_sort_key)

    # Trimmed object for the client; rendered via {{ ...|json_script }} (safe).
    report_groups_data = [
        {"label": g, "reports": [{"id": r["id"], "name": r["name"]} for r in groups_map[g]]}
        for g in sorted_groups
    ]

    from engine.engines.email_service import is_smtp_configured

    return render(
        request,
        "workspace/reports.html",
        {
            "reports": report_list,
            "report_groups": report_groups_data,
            "has_access": True,
            "email_enabled": is_smtp_configured(),
        },
    )


@login_required
def report_latest_view(request: HttpRequest, definition_id: int) -> HttpResponse:
    """HTMX endpoint — returns latest successful execution as HTML table."""
    from engine.models import ReportDefinition

    user = cast("AbstractUser", request.user)
    report = ReportDefinition.objects.filter(pk=definition_id, is_active=True).first()
    if not report:
        return HttpResponse("<p>Report not found.</p>", status=404)

    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile or not profile.get_allowed_reports().filter(pk=definition_id).exists():
            return HttpResponse("<p>Access denied.</p>", status=403)

    execution = report.get_latest_execution()
    if not execution:
        return HttpResponse(
            '<div class="docs-empty-state">'  # noqa: E501
            "<p>No results yet. This report has not been run.</p></div>"
        )

    from engine.engines.email_service import is_smtp_configured

    return render(
        request,
        "workspace/reports_result_table.html",
        {
            "execution": execution,
            "report": {"name": report.name, "description": report.description},
            "email_enabled": is_smtp_configured(),
        },
    )


@login_required
def report_history_view(request: HttpRequest, definition_id: int) -> HttpResponse:
    """HTMX endpoint — lists past executions for a report."""
    from engine.models import ReportDefinition

    user = cast("AbstractUser", request.user)
    report = ReportDefinition.objects.filter(pk=definition_id, is_active=True).first()
    if not report:
        return HttpResponse("<p>Report not found.</p>", status=404)

    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile or not profile.get_allowed_reports().filter(pk=definition_id).exists():
            return HttpResponse("<p>Access denied.</p>", status=403)

    executions = report.executions.order_by("-started_at")[:20]
    html_parts = [f'<h3 style="margin-bottom: var(--md);">History: {report.name}</h3>']

    if not executions:
        html_parts.append('<p class="text-sec">No executions yet.</p>')
    else:
        html_parts.append('<div class="report-table-wrap"><table class="report-table"><thead><tr>')
        html_parts.append("<th>Status</th><th>Started</th><th>Duration</th><th>Rows</th><th></th>")
        html_parts.append("</tr></thead><tbody>")
        for ex in executions:
            badge_css = (
                "badge-success"
                if ex.status == "success"
                else ("badge-error" if ex.status == "failed" else "badge-muted")
            )
            duration = (
                f"{ex.execution_time_ms}ms" if ex.execution_time_ms is not None else "&mdash;"
            )
            rows = str(ex.row_count) if ex.row_count is not None else "&mdash;"
            html_parts.append(
                f'<tr><td><span class="badge {badge_css}">{ex.status.upper()}</span></td>'
            )
            html_parts.append(f"<td>{ex.started_at.strftime('%b %d, %H:%M')}</td>")
            html_parts.append(f"<td>{duration}</td><td>{rows}</td>")
            html_parts.append(
                f'<td><button class="btn btn-ghost btn-sm" onclick="loadExecution({ex.pk})">View</button></td></tr>'  # noqa: E501
            )
        html_parts.append("</tbody></table></div>")

    return HttpResponse("".join(html_parts))


@login_required
def report_execution_content_view(request: HttpRequest, execution_id: int) -> HttpResponse:
    """HTMX endpoint — returns a specific execution's results."""
    from engine.models import ReportExecution

    user = cast("AbstractUser", request.user)
    execution = ReportExecution.objects.select_related("definition").filter(pk=execution_id).first()
    if not execution:
        return HttpResponse("<p>Execution not found.</p>", status=404)

    report = execution.definition
    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile or not profile.get_allowed_reports().filter(pk=report.pk).exists():
            return HttpResponse("<p>Access denied.</p>", status=403)

    from engine.engines.email_service import is_smtp_configured

    return render(
        request,
        "workspace/reports_result_table.html",
        {
            "execution": execution,
            "report": {"name": report.name, "description": report.description},
            "email_enabled": is_smtp_configured(),
        },
    )


@login_required
def report_download_view(request: HttpRequest, execution_id: int, fmt: str) -> HttpResponse:
    """Download a report execution as CSV or Excel."""
    from engine.models import ReportExecution

    user = cast("AbstractUser", request.user)
    execution = ReportExecution.objects.select_related("definition").filter(pk=execution_id).first()
    if not execution:
        return HttpResponse("Execution not found.", status=404)

    report = execution.definition
    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile or not profile.get_allowed_reports().filter(pk=report.pk).exists():
            return HttpResponse("Access denied.", status=403)

    from engine.engines.result_storage import load_meta, load_rows

    meta = load_meta(execution.pk)
    if not meta or not meta["column_names"]:
        return HttpResponse("No data to download.", status=404)

    column_names = meta["column_names"]
    rows = load_rows(execution.pk)
    safe_name = re.sub(r"[^\w\-]", "_", report.name)

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(column_names)
        writer.writerows(rows)
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.csv"'
        return response

    elif fmt == "excel":
        try:
            import openpyxl
        except ImportError:
            return HttpResponse("Excel export not available (openpyxl not installed).", status=500)

        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = safe_name[:31]
        ws.append(column_names)
        for row in rows:
            ws.append(row)

        buf_bytes = io.BytesIO()
        wb.save(buf_bytes)
        buf_bytes.seek(0)
        response = HttpResponse(
            buf_bytes.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.xlsx"'
        return response

    return HttpResponse("Invalid format.", status=400)


@login_required
@require_http_methods(["POST"])
def report_send_email_view(request: HttpRequest, execution_id: int) -> HttpResponse:
    """Send report results to the logged-in user's email."""
    from engine.models import ReportExecution

    user = cast("AbstractUser", request.user)
    if not user.email:
        return JsonResponse({"error": "Your account has no email address configured."}, status=400)

    from engine.engines.email_service import is_smtp_configured

    if not is_smtp_configured():
        return JsonResponse(
            {"error": "Email is not available. Contact your administrator."}, status=400
        )

    execution = ReportExecution.objects.select_related("definition").filter(pk=execution_id).first()
    if not execution:
        return JsonResponse({"error": "Execution not found."}, status=404)

    report = execution.definition
    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile or not profile.get_allowed_reports().filter(pk=report.pk).exists():
            return JsonResponse({"error": "Access denied."}, status=403)

    from engine.tasks import send_report_email_task

    cast(Any, send_report_email_task).delay(execution.pk, [user.email])
    return JsonResponse({"message": f"Report will be sent to {user.email} shortly."})
