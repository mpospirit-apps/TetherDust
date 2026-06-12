"""Report definition CRUD + run/preview/toggle + execution monitoring."""

from __future__ import annotations

from core.models import ReportDefinition, ReportExecution
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import ReportDefinitionForm


@staff_member_required(login_url="/login/")
def report_list_view(request: HttpRequest) -> HttpResponse:
    reports = ReportDefinition.objects.select_related("database").all()
    for report in reports:
        report.latest_exec = report.get_latest_execution()
    return render(
        request,
        "console/reports/list.html",
        {
            "reports": reports,
            "section": "reports",
        },
    )


@staff_member_required(login_url="/login/")
def report_form_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    instance = get_object_or_404(ReportDefinition, pk=pk) if pk else None
    if request.method == "POST":
        form = ReportDefinitionForm(request.POST, instance=instance)
        if form.is_valid():
            report: ReportDefinition = form.save(commit=False)  # type: ignore[assignment]
            if not instance:
                report.created_by = request.user
            if report.schedule_type != "manual":
                from core.engines.report_engine import compute_next_run

                report.next_run_at = compute_next_run(report)
            else:
                report.next_run_at = None
            report.save()
            form.save_m2m()
            return redirect("console:report_list")
    else:
        form = ReportDefinitionForm(instance=instance)

    return render(
        request,
        "console/reports/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "reports",
        },
    )


@staff_member_required(login_url="/login/")
@require_POST
def report_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ReportDefinition, pk=pk)
    obj.delete()
    return redirect("console:report_list")


@staff_member_required(login_url="/login/")
@require_POST
def report_run_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Manually trigger a report execution."""
    from core.engines.report_engine import execute_report

    report = get_object_or_404(ReportDefinition, pk=pk)
    execution = execute_report(report, triggered_by=request.user)
    return redirect("console:report_execution_detail", pk=execution.pk)


@staff_member_required(login_url="/login/")
def report_preview_view(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX endpoint — runs report SQL with LIMIT 10, returns table fragment."""
    from core.engines.report_engine import execute_report

    report = get_object_or_404(ReportDefinition, pk=pk)
    execution = execute_report(report, triggered_by=request.user, max_rows_override=10)

    if execution.status == "failed":
        return HttpResponse(
            f'<span class="badge badge-error">Error: {execution.error_message}</span>'
        )

    return render(
        request,
        "portal/reports_result_table.html",
        {
            "execution": execution,
            "report": report,
            "is_preview": True,
        },
    )


@staff_member_required(login_url="/login/")
@require_POST
def report_toggle_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle report active/inactive via HTMX."""
    obj = get_object_or_404(ReportDefinition, pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    status = "active" if obj.is_active else "inactive"
    css = "badge-success" if obj.is_active else "badge-muted"
    return HttpResponse(f'<span class="badge {css}">{status.upper()}</span>')


@staff_member_required(login_url="/login/")
def report_execution_list_view(request: HttpRequest) -> HttpResponse:
    executions = ReportExecution.objects.select_related("definition", "triggered_by").order_by(
        "-started_at"
    )[:200]
    return render(
        request,
        "console/reports/execution_list.html",
        {
            "executions": executions,
            "section": "report_runs",
        },
    )


@staff_member_required(login_url="/login/")
def report_execution_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    execution = get_object_or_404(
        ReportExecution.objects.select_related("definition", "triggered_by"),
        pk=pk,
    )
    return render(
        request,
        "console/reports/execution_detail.html",
        {
            "execution": execution,
            "section": "report_runs",
        },
    )
