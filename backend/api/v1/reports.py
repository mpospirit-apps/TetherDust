"""Public reports API — role-scoped list + latest/history/execution results,
CSV/Excel download, and on-demand email.

Replaces ``workspace/views/reports.py``. Result rows are loaded from the
filesystem (``engine.engines.result_storage``); the table endpoints return a
capped preview (``row_count`` carries the true total) while downloads stream the
full data. Email delivery is dispatched to Celery (``send_report_email_task``).
"""

from __future__ import annotations

import csv
import io
import re
from typing import TYPE_CHECKING, Any, cast

from engine.engines.email_service import is_smtp_configured
from engine.engines.result_storage import load_meta, load_rows
from engine.models import ReportDefinition, ReportExecution
from engine.services import PermissionService, ReportService, get
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewReports

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db.models import QuerySet
    from django.http import HttpResponse

PREVIEW_ROWS = 25


def _visible_reports(user: AbstractUser) -> QuerySet[ReportDefinition]:
    """Active reports the user may see (staff → all; else role-allowed)."""
    if user.is_staff:
        return ReportDefinition.objects.filter(is_active=True).select_related("database")
    profile = getattr(user, "profile", None)
    if not profile or not get(PermissionService).can_view_reports(profile):
        return ReportDefinition.objects.none()
    return get(PermissionService).get_allowed_reports(profile).select_related("database")


def _can_view_report(user: AbstractUser, report: ReportDefinition) -> bool:
    if user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    return bool(
        profile
        and get(PermissionService).get_allowed_reports(profile).filter(pk=report.pk).exists()
    )


def _latest_summary(report: ReportDefinition) -> dict[str, Any] | None:
    execution = get(ReportService).get_latest_execution(report)
    if execution is None:
        return None
    return {
        "id": execution.pk,
        "status": execution.status,
        "started_at": execution.started_at.isoformat(),
        "row_count": execution.row_count,
        "execution_time_ms": execution.execution_time_ms,
    }


def _execution_payload(execution: ReportExecution) -> dict[str, Any]:
    """Execution metadata + a capped row preview for table rendering."""
    meta = load_meta(execution.pk) if execution.result_file_path else None
    column_names = meta["column_names"] if meta else []
    rows = load_rows(execution.pk, limit=PREVIEW_ROWS) if meta else []
    return {
        "id": execution.pk,
        "status": execution.status,
        "row_count": execution.row_count,
        "execution_time_ms": execution.execution_time_ms,
        "started_at": execution.started_at.isoformat(),
        "completed_at": (execution.completed_at.isoformat() if execution.completed_at else None),
        "error_message": execution.error_message,
        "column_names": column_names,
        "rows": rows,
        "preview_limit": PREVIEW_ROWS,
    }


class ReportsView(APIView):
    """Role-scoped report list with each report's latest successful run."""

    permission_classes = [CanViewReports]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        reports = _visible_reports(user).order_by("name")
        return Response(
            {
                "email_enabled": is_smtp_configured(),
                "reports": [
                    {
                        "id": report.pk,
                        "name": report.name,
                        "description": report.description,
                        "database": report.database.name,
                        "latest_run": _latest_summary(report),
                    }
                    for report in reports
                ],
            }
        )


class ReportLatestView(APIView):
    """Latest successful execution for a report (role-checked)."""

    permission_classes = [CanViewReports]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        report = ReportDefinition.objects.filter(pk=pk, is_active=True).first()
        if report is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _can_view_report(user, report):
            return Response({"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        execution = get(ReportService).get_latest_execution(report)
        return Response(
            {
                "report": {"name": report.name, "description": report.description},
                "email_enabled": is_smtp_configured(),
                "execution": _execution_payload(execution) if execution else None,
            }
        )


class ReportHistoryView(APIView):
    """Recent executions for a report (role-checked)."""

    permission_classes = [CanViewReports]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        report = ReportDefinition.objects.filter(pk=pk, is_active=True).first()
        if report is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _can_view_report(user, report):
            return Response({"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        executions = report.executions.order_by("-started_at")[:20]
        return Response(
            {
                "report": {"name": report.name, "description": report.description},
                "executions": [
                    {
                        "id": ex.pk,
                        "status": ex.status,
                        "started_at": ex.started_at.isoformat(),
                        "execution_time_ms": ex.execution_time_ms,
                        "row_count": ex.row_count,
                    }
                    for ex in executions
                ],
            }
        )


def _execution_for_user(user: AbstractUser, pk: str) -> ReportExecution | None:
    execution = (
        ReportExecution.objects.select_related("definition", "definition__database")
        .filter(pk=pk)
        .first()
    )
    if execution is None or not _can_view_report(user, execution.definition):
        return None
    return execution


class ExecutionDetailView(APIView):
    """A specific execution's results (role-checked via its report)."""

    permission_classes = [CanViewReports]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        execution = _execution_for_user(user, pk)
        if execution is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        report = execution.definition
        return Response(
            {
                "report": {"name": report.name, "description": report.description},
                "email_enabled": is_smtp_configured(),
                "execution": _execution_payload(execution),
            }
        )


class ExecutionDownloadView(APIView):
    """Download a full execution as CSV or Excel (role-checked).

    Returns a raw file response; DRF passes non-``Response`` results through
    unchanged. Triggered same-origin so the session cookie authenticates the GET.
    """

    permission_classes = [CanViewReports]

    def get(self, request: Request, pk: str, fmt: str) -> HttpResponse:
        from django.http import HttpResponse

        user = cast("AbstractUser", request.user)
        execution = _execution_for_user(user, pk)
        if execution is None:
            return HttpResponse("Execution not found.", status=404)

        meta = load_meta(execution.pk)
        if not meta or not meta["column_names"]:
            return HttpResponse("No data to download.", status=404)

        column_names = meta["column_names"]
        rows = load_rows(execution.pk)
        safe_name = re.sub(r"[^\w\-]", "_", execution.definition.name)

        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(column_names)
            writer.writerows(rows)
            response = HttpResponse(buf.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}.csv"'
            return response

        if fmt == "excel":
            try:
                import openpyxl
            except ImportError:
                return HttpResponse(
                    "Excel export not available (openpyxl not installed).", status=500
                )

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
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )
            response["Content-Disposition"] = f'attachment; filename="{safe_name}.xlsx"'
            return response

        return HttpResponse("Invalid format.", status=400)


class ExecutionEmailView(APIView):
    """Email a report execution to the logged-in user (role-checked)."""

    permission_classes = [CanViewReports]

    def post(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        if not user.email:
            return Response(
                {"detail": "Your account has no email address configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not is_smtp_configured():
            return Response(
                {"detail": "Email is not available. Contact your administrator."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        execution = _execution_for_user(user, pk)
        if execution is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from engine.tasks import send_report_email_task

        cast(Any, send_report_email_task).delay(execution.pk, [user.email])
        return Response({"detail": f"Report will be sent to {user.email} shortly."})
