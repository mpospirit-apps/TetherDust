"""Dashboard + chart admin API: CRUD, ad-hoc preview, chart data, AI generation.

Ports ``management/views/dashboard.py``. Charts are custom-d3 (the model's other
``chart_type`` values are legacy); SQL is validated read-only via the serializer.
AI generation is delegated to ``engine.engines.chartgen`` and tracked by
``ChartGenerationLog``, polled through the ``status`` action.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet
from engine.engines import chartgen
from engine.engines.charts import chart_data, preview_query
from engine.models import (
    AgentConfiguration,
    Chart,
    ChartGenerationLog,
    Codebase,
    Dashboard,
    DatabaseConnection,
    DocumentationSource,
)
from engine.prompts import DASHBOARD_TEMPLATES
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


def _resolve_names(model: Any, field: str, ids: list[str]) -> list[str]:
    return list(model.objects.filter(pk__in=ids, is_active=True).values_list(field, flat=True))


class DashboardSerializer(serializers.ModelSerializer[Dashboard]):
    chart_count = serializers.IntegerField(read_only=True)

    class Meta(SerializerMeta):
        model = Dashboard
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "auto_refresh",
            "refresh_interval",
            "allowed_roles",
            "chart_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "chart_count", "created_at", "updated_at"]


class DashboardViewSet(viewsets.ModelViewSet[Dashboard]):
    """Staff CRUD for dashboards, plus AI generation + its options."""

    permission_classes = [IsStaffUser]
    serializer_class = DashboardSerializer

    def get_queryset(self) -> QuerySet[Dashboard]:
        return Dashboard.objects.annotate(chart_count=Count("charts")).order_by("name")

    def perform_create(self, serializer: Any) -> None:
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="generate-options")
    def generate_options(self, request: Request) -> Response:
        return Response(
            {
                "databases": [
                    {"id": d.pk, "name": d.name}
                    for d in DatabaseConnection.objects.filter(is_active=True)
                ],
                "doc_sources": [
                    {"id": s.pk, "name": s.folder_name}
                    for s in DocumentationSource.objects.filter(is_active=True)
                ],
                "codebases": [
                    {"id": c.pk, "name": c.name} for c in Codebase.objects.filter(is_active=True)
                ],
                "agents": [
                    {"id": a.pk, "name": a.name, "is_active": a.is_active}
                    for a in AgentConfiguration.objects.all()
                ],
                "dashboard_types": sorted(DASHBOARD_TEMPLATES),
            }
        )

    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        data = request.data
        dashboard_name = (data.get("dashboard_name") or "").strip()
        agent_id = data.get("agent")
        if not all([dashboard_name, agent_id]):
            return Response(
                {"detail": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST
            )
        if Dashboard.objects.filter(name=dashboard_name).exists():
            return Response(
                {"detail": f"A dashboard named '{dashboard_name}' already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        agent_config = AgentConfiguration.objects.filter(pk=agent_id).first()
        if agent_config is None:
            return Response({"detail": "Agent not found."}, status=status.HTTP_404_NOT_FOUND)

        log = chartgen.start_generation(
            user=cast(User, request.user),
            agent_config=agent_config,
            dashboard_name=dashboard_name,
            dashboard_type=data.get("dashboard_type", "overview"),
            prompt_override=data.get("prompt_override", ""),
            db_names=_resolve_names(DatabaseConnection, "name", data.get("source_db", [])),
            doc_names=_resolve_names(
                DocumentationSource, "folder_name", data.get("source_doc", [])
            ),
            codebase_names=_resolve_names(Codebase, "name", data.get("source_codebase", [])),
        )
        return Response({"log_id": log.pk}, status=status.HTTP_202_ACCEPTED)


class ChartSerializer(serializers.ModelSerializer[Chart]):
    database_name = serializers.CharField(source="database.name", read_only=True)

    class Meta(SerializerMeta):
        model = Chart
        fields = [
            "id",
            "dashboard",
            "database",
            "database_name",
            "title",
            "description",
            "sql_query",
            "custom_d3_code",
            "chart_type",
            "width",
            "height",
            "position",
            "is_active",
            "last_error",
            "last_refreshed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "database_name",
            "last_error",
            "last_refreshed_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        from engine.engines.report_engine import validate_sql

        sql = attrs.get("sql_query", getattr(self.instance, "sql_query", ""))
        db = attrs.get("database", getattr(self.instance, "database", None))
        if sql:
            error = validate_sql(sql, engine=db.engine if db else None)
            if error:
                raise serializers.ValidationError({"sql_query": error})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Chart:
        validated_data.setdefault("chart_type", "custom")
        return super().create(validated_data)


class ChartViewSet(viewsets.ModelViewSet[Chart]):
    """Staff CRUD for charts (filter by ``?dashboard=``), plus preview + data."""

    permission_classes = [IsStaffUser]
    serializer_class = ChartSerializer

    def get_queryset(self) -> QuerySet[Chart]:
        qs = Chart.objects.select_related("database", "dashboard")
        dashboard_id = self.request.query_params.get("dashboard")
        if dashboard_id:
            qs = qs.filter(dashboard_id=dashboard_id)
        return qs.order_by("position", "title")

    @action(detail=False, methods=["post"])
    def preview(self, request: Request) -> Response:
        """Run an ad-hoc ``{database, sql_query}`` query for the editor preview."""
        database_id = request.data.get("database")
        sql = (request.data.get("sql_query") or "").strip()
        if not database_id:
            return Response({"error": "database is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not sql:
            return Response({"error": "sql_query is required."}, status=status.HTTP_400_BAD_REQUEST)
        db_conn = DatabaseConnection.objects.filter(pk=database_id).first()
        if db_conn is None:
            return Response({"error": "Database not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Response(preview_query(db_conn, sql))
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["get"])
    def data(self, request: Request, pk: str | None = None) -> Response:
        chart = self.get_object()
        force_refresh = request.query_params.get("refresh") == "1"
        try:
            return Response(chart_data(chart, force_refresh))
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChartGenerationLogSerializer(serializers.ModelSerializer[ChartGenerationLog]):
    user = serializers.CharField(source="user.username", read_only=True, default=None)
    agent = serializers.CharField(source="agent.name", read_only=True, default=None)

    class Meta(SerializerMeta):
        model = ChartGenerationLog
        fields = [
            "id",
            "status",
            "dashboard_name",
            "charts_created",
            "execution_time_ms",
            "error_message",
            "user",
            "agent",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class ChartGenerationLogDetailSerializer(serializers.ModelSerializer[ChartGenerationLog]):
    """Full record for the detail page — adds the prompt, agent output, and sources."""

    user = serializers.CharField(source="user.username", read_only=True, default=None)
    agent = serializers.CharField(source="agent.name", read_only=True, default=None)

    class Meta(SerializerMeta):
        model = ChartGenerationLog
        fields = [
            "id",
            "status",
            "dashboard_name",
            "charts_created",
            "execution_time_ms",
            "error_message",
            "errors",
            "source_databases",
            "source_docs",
            "prompt_used",
            "agent_output",
            "user",
            "agent",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class ChartGenerationLogViewSet(viewsets.ReadOnlyModelViewSet[ChartGenerationLog]):
    """Read-only dashboard-generation history + a ``status`` payload for polling.

    ``list`` uses the lean serializer; ``retrieve`` returns the full record
    (prompt + agent output can be large, so they're detail-only).
    """

    permission_classes = [IsStaffUser]
    serializer_class = ChartGenerationLogSerializer
    queryset = ChartGenerationLog.objects.select_related("user", "agent").all()

    def get_serializer_class(self) -> type[serializers.BaseSerializer[ChartGenerationLog]]:
        if self.action == "retrieve":
            return ChartGenerationLogDetailSerializer
        return ChartGenerationLogSerializer

    @action(detail=True, methods=["get"])
    def status(self, request: Request, pk: str | None = None) -> Response:
        return Response(chartgen.status_payload(self.get_object()))
