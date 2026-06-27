"""Report admin API: definition CRUD + run/preview/toggle, and execution monitor.

Ports ``management/views/report.py`` + ``management/forms/reports.py``. Email
recipients live inside ``delivery_config`` (a write-only list field merges them);
SQL is validated read-only via ``report_engine.validate_sql``; ``next_run_at`` is
recomputed from the schedule on every save (mirroring the legacy view).
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from engine.models import ReportDefinition, ReportExecution
from engine.services import ReportService, get
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta
from api.v1.reports import _execution_payload


def _latest_run(report: ReportDefinition) -> dict[str, Any] | None:
    execution = get(ReportService).get_latest_execution(report)
    if execution is None:
        return None
    return {
        "id": execution.pk,
        "status": execution.status,
        "started_at": execution.started_at.isoformat(),
        "row_count": execution.row_count,
    }


class ReportDefinitionSerializer(serializers.ModelSerializer[ReportDefinition]):
    database_name = serializers.CharField(source="database.name", read_only=True)
    email_recipients = serializers.ListField(
        child=serializers.EmailField(), required=False, write_only=True
    )
    latest_run = serializers.SerializerMethodField()

    class Meta(SerializerMeta):
        model = ReportDefinition
        fields = [
            "id",
            "name",
            "description",
            "database",
            "database_name",
            "sql_query",
            "schedule_type",
            "schedule_interval_minutes",
            "schedule_time",
            "schedule_day_of_week",
            "schedule_day_of_month",
            "next_run_at",
            "delivery_method",
            "is_active",
            "allowed_roles",
            "email_recipients",
            "latest_run",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "database_name",
            "next_run_at",
            "latest_run",
            "created_at",
            "updated_at",
        ]

    def get_latest_run(self, obj: ReportDefinition) -> dict[str, Any] | None:
        return _latest_run(obj)

    def to_representation(self, instance: ReportDefinition) -> dict[str, Any]:
        data = super().to_representation(instance)
        config = instance.delivery_config or {}
        data["email_recipients"] = config.get("email_recipients", [])
        return data

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        from engine.engines.report_engine import validate_sql

        sql = attrs.get("sql_query", getattr(self.instance, "sql_query", ""))
        db = attrs.get("database", getattr(self.instance, "database", None))
        if sql:
            error = validate_sql(sql, engine=db.engine if db else None)
            if error:
                raise serializers.ValidationError({"sql_query": error})
        return attrs

    def _store_recipients(self, instance: ReportDefinition, recipients: list[str]) -> None:
        config = dict(instance.delivery_config or {})
        config["email_recipients"] = recipients
        instance.delivery_config = config
        instance.save(update_fields=["delivery_config"])

    def create(self, validated_data: dict[str, Any]) -> ReportDefinition:
        recipients = validated_data.pop("email_recipients", [])
        instance = super().create(validated_data)
        self._store_recipients(instance, recipients)
        return instance

    def update(
        self, instance: ReportDefinition, validated_data: dict[str, Any]
    ) -> ReportDefinition:
        recipients = validated_data.pop("email_recipients", None)
        instance = super().update(instance, validated_data)
        if recipients is not None:
            self._store_recipients(instance, recipients)
        return instance


class ReportDefinitionViewSet(viewsets.ModelViewSet[ReportDefinition]):
    """Staff CRUD for report definitions, plus run / preview / toggle."""

    permission_classes = [IsStaffUser]
    serializer_class = ReportDefinitionSerializer

    def get_queryset(self) -> QuerySet[ReportDefinition]:
        return ReportDefinition.objects.select_related("database").order_by("name")

    def perform_create(self, serializer: Any) -> None:
        report = serializer.save(created_by=self.request.user)
        self._apply_schedule(report)

    def perform_update(self, serializer: Any) -> None:
        report = serializer.save()
        self._apply_schedule(report)

    @staticmethod
    def _apply_schedule(report: ReportDefinition) -> None:
        from engine.engines.report_engine import compute_next_run

        report.next_run_at = compute_next_run(report) if report.schedule_type != "manual" else None
        report.save(update_fields=["next_run_at"])

    @action(detail=True, methods=["post"])
    def run(self, request: Request, pk: str | None = None) -> Response:
        """Run the report now and return the resulting execution."""
        from engine.engines.report_engine import execute_report

        report = self.get_object()
        execution = execute_report(report, triggered_by=cast(User, request.user))
        return Response(_execution_payload(execution), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def preview(self, request: Request, pk: str | None = None) -> Response:
        """Run the report SQL with a 10-row cap for an editor preview."""
        from engine.engines.report_engine import execute_report

        report = self.get_object()
        execution = execute_report(
            report, triggered_by=cast(User, request.user), max_rows_override=10
        )
        return Response(_execution_payload(execution))

    @action(detail=True, methods=["post"])
    def toggle(self, request: Request, pk: str | None = None) -> Response:
        report = self.get_object()
        report.is_active = not report.is_active
        report.save(update_fields=["is_active"])
        return Response({"is_active": report.is_active})


class ReportExecutionSerializer(serializers.ModelSerializer[ReportExecution]):
    report_name = serializers.CharField(source="definition.name", read_only=True)
    triggered_by = serializers.CharField(
        source="triggered_by.username", read_only=True, default=None
    )

    class Meta(SerializerMeta):
        model = ReportExecution
        fields = [
            "id",
            "definition",
            "report_name",
            "status",
            "started_at",
            "completed_at",
            "execution_time_ms",
            "row_count",
            "error_message",
            "triggered_by",
        ]
        read_only_fields = fields


class ReportExecutionViewSet(viewsets.ReadOnlyModelViewSet[ReportExecution]):
    """Read-only execution monitor (filter by ``?definition=``).

    Row-level results are served by the public ``/executions/<id>/`` endpoint
    (staff pass the role check there); this viewset carries the run metadata list.
    """

    permission_classes = [IsStaffUser]
    serializer_class = ReportExecutionSerializer

    def get_queryset(self) -> QuerySet[ReportExecution]:
        qs = ReportExecution.objects.select_related("definition", "triggered_by").order_by(
            "-started_at"
        )
        definition = self.request.query_params.get("definition")
        if definition:
            qs = qs.filter(definition_id=definition)
        return qs
