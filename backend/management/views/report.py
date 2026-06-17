"""Report definition CRUD + run/preview/toggle + execution monitoring."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from engine.models import ReportDefinition, ReportExecution
from engine.services import ReportService, get

from management.views._helpers import staff_required

from ..forms import ReportDefinitionForm


@staff_required
def report_list_view(request: HttpRequest) -> HttpResponse:
    reports = ReportDefinition.objects.select_related("database").all()
    for report in reports:
        report.latest_exec = get(ReportService).get_latest_execution(report)
    return render(
        request,
        "management/reports/list.html",
        {
            "reports": reports,
            "section": "reports",
        },
    )


@staff_required
def report_form_view(request: HttpRequest, pk: str | None = None) -> HttpResponse:
    instance = get_object_or_404(ReportDefinition, pk=pk) if pk else None
    if request.method == "POST":
        form = ReportDefinitionForm(request.POST, instance=instance)
        if form.is_valid():
            report = form.save(commit=False)
            assert isinstance(report, ReportDefinition)
            if not instance:
                report.created_by = cast(User, request.user)
            if report.schedule_type != "manual":
                from engine.engines.report_engine import compute_next_run

                report.next_run_at = compute_next_run(report)
            else:
                report.next_run_at = None
            report.save()
            form.save_m2m()
            return redirect("management:report_list")
    else:
        form = ReportDefinitionForm(instance=instance)

    return render(
        request,
        "management/reports/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "reports",
        },
    )


@staff_required
@require_POST
def report_delete_view(request: HttpRequest, pk: str) -> HttpResponse:
    obj = get_object_or_404(ReportDefinition, pk=pk)
    obj.delete()
    return redirect("management:report_list")


@staff_required
@require_POST
def report_run_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Manually trigger a report execution."""
    from engine.engines.report_engine import execute_report

    report = get_object_or_404(ReportDefinition, pk=pk)
    user = request.user if isinstance(request.user, User) else None
    execution = execute_report(report, triggered_by=user)
    return redirect("management:report_execution_detail", pk=execution.pk)


@staff_required
def report_preview_view(request: HttpRequest, pk: str) -> HttpResponse:
    """HTMX endpoint — runs report SQL with LIMIT 10, returns table fragment."""
    from engine.engines.report_engine import execute_report

    report = get_object_or_404(ReportDefinition, pk=pk)
    user = request.user if isinstance(request.user, User) else None
    execution = execute_report(report, triggered_by=user, max_rows_override=10)

    if execution.status == "failed":
        return HttpResponse(
            f'<span class="badge badge-error">Error: {execution.error_message}</span>'
        )

    return render(
        request,
        "workspace/reports_result_table.html",
        {
            "execution": execution,
            "column_names": get(ReportService).column_names(execution),
            "result_data": get(ReportService).result_data(execution),
            "report": report,
            "is_preview": True,
        },
    )


@staff_required
@require_POST
def report_toggle_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Toggle report active/inactive via HTMX."""
    obj = get_object_or_404(ReportDefinition, pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    status = "active" if obj.is_active else "inactive"
    css = "badge-success" if obj.is_active else "badge-muted"
    return HttpResponse(f'<span class="badge {css}">{status.upper()}</span>')


@staff_required
def report_execution_list_view(request: HttpRequest) -> HttpResponse:
    executions = ReportExecution.objects.select_related("definition", "triggered_by").order_by(
        "-started_at"
    )[:200]
    return render(
        request,
        "management/reports/execution_list.html",
        {
            "executions": executions,
            "section": "report_runs",
        },
    )


@staff_required
def report_execution_detail_view(request: HttpRequest, pk: str) -> HttpResponse:
    execution = get_object_or_404(
        ReportExecution.objects.select_related("definition", "triggered_by"),
        pk=pk,
    )
    return render(
        request,
        "management/reports/execution_detail.html",
        {
            "execution": execution,
            "column_names": get(ReportService).column_names(execution),
            "result_data": get(ReportService).result_data(execution),
            "section": "report_runs",
        },
    )
