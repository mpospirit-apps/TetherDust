"""Internal write endpoints backing the tdmcp mutating tools.

Each view replaces a raw-SQL write that previously lived in ``tdmcp/tools/*``.
Business rules (duplicate-name checks, read-only SQL validation, tether-graph
schema validation, version promotion) are reused from ``engine`` so there is a
single source of truth. Responses carry the same ``{"success": ..., ...}`` shape
the agent already expects, so the tdmcp side just relays the JSON.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.db import transaction
from engine.engines.report_engine import validate_sql
from engine.engines.tether_engine import TetherSchemaError
from engine.engines.tether_engine import validate as validate_graph
from engine.models import Chart, Dashboard, DatabaseConnection, TetherVersion
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import IsServiceToken, ServiceTokenAuthentication

_VALID_WIDTHS = {3, 4, 6, 8, 12}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _InternalView(APIView):
    """Base: service-token auth only (no session/CSRF)."""

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsServiceToken]


class DashboardCreateView(_InternalView):
    """``create_dashboard`` — create a dashboard container."""

    def post(self, request: Request) -> Response:
        name = (request.data.get("name") or "").strip()
        description = request.data.get("description") or ""
        if not name:
            return Response(
                {"success": False, "error": "A dashboard name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = Dashboard.objects.filter(name=name).first()
        if existing is not None:
            return Response(
                {
                    "success": False,
                    "error": f"A dashboard named '{name}' already exists (id={existing.id}).",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        dashboard = Dashboard.objects.create(
            name=name, description=description, is_active=True, auto_refresh=False
        )
        return Response(
            {"success": True, "dashboard_id": dashboard.id, "name": dashboard.name},
            status=status.HTTP_201_CREATED,
        )


class ChartCreateView(_InternalView):
    """``add_chart`` — add a custom d3.js chart to a dashboard."""

    def post(self, request: Request, dashboard_id: str) -> Response:
        dashboard = Dashboard.objects.filter(id=dashboard_id).first()
        if dashboard is None:
            return Response(
                {"success": False, "error": f"Dashboard with id={dashboard_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        title = (request.data.get("title") or "").strip()
        if not title:
            return Response(
                {"success": False, "error": "A chart title is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        database = (request.data.get("database") or "").strip()
        connection = DatabaseConnection.objects.filter(name=database, is_active=True).first()
        if connection is None:
            return Response(
                {
                    "success": False,
                    "error": f"Database connection '{database}' not found or inactive.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        sql_query = request.data.get("sql_query") or ""
        sql_error = validate_sql(sql_query, connection.engine)
        if sql_error:
            return Response(
                {"success": False, "error": sql_error}, status=status.HTTP_400_BAD_REQUEST
            )

        width = _as_int(request.data.get("width", 6), 6)
        if width not in _VALID_WIDTHS:
            width = 6

        chart = Chart.objects.create(
            dashboard=dashboard,
            title=title,
            description=request.data.get("description") or "",
            sql_query=sql_query,
            chart_type="custom",
            custom_d3_code=request.data.get("d3_code") or "",
            database=connection,
            position=_as_int(request.data.get("position", 0), 0),
            width=width,
            height=_as_int(request.data.get("height", 300), 300),
            is_active=True,
        )
        return Response(
            {
                "success": True,
                "chart_id": chart.id,
                "title": chart.title,
                "dashboard_id": dashboard.id,
            },
            status=status.HTTP_201_CREATED,
        )


class ChartUpdateView(_InternalView):
    """``update_chart`` — patch an existing chart's editable fields."""

    def patch(self, request: Request, chart_id: str) -> Response:
        chart = Chart.objects.filter(id=chart_id).select_related("database").first()
        if chart is None:
            return Response(
                {"success": False, "error": f"Chart with id={chart_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data
        updated_fields: list[str] = []

        title = data.get("title")
        if title is not None:
            chart.title = title
            updated_fields.append("title")
        description = data.get("description")
        if description is not None:
            chart.description = description
            updated_fields.append("description")
        sql_query = data.get("sql_query")
        if sql_query is not None:
            sql_error = validate_sql(sql_query, chart.database.engine)
            if sql_error:
                return Response(
                    {"success": False, "error": sql_error}, status=status.HTTP_400_BAD_REQUEST
                )
            chart.sql_query = sql_query
            # Invalidate cache so the dashboard re-runs the query on next load.
            chart.cached_data = {}
            chart.last_refreshed_at = None
            chart.last_error = ""
            updated_fields.append("sql_query")
        d3_code = data.get("d3_code")
        if d3_code is not None:
            chart.custom_d3_code = d3_code
            updated_fields.append("d3_code")

        if not updated_fields:
            return Response(
                {
                    "success": False,
                    "error": "Nothing to update. Provide at least one of: title, "
                    "description, sql_query, d3_code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        chart.save()
        return Response(
            {"success": True, "chart_id": chart.id, "updated_fields": updated_fields},
            status=status.HTTP_200_OK,
        )


class TetherGraphSaveView(_InternalView):
    """``save_tether_graph`` — persist a generated graph + promote the version."""

    def post(self, request: Request, version_id: str) -> Response:
        version = TetherVersion.objects.filter(id=version_id).select_related("tether").first()
        if version is None:
            return Response(
                {"success": False, "error": f"TetherVersion {version_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        nodes = request.data.get("nodes") or []
        edges = request.data.get("edges") or []
        now = datetime.now(UTC)
        graph: dict[str, Any] = {
            "schema_version": 2,
            "generated_at": now.isoformat(),
            "codebase_summary": request.data.get("codebase_summary") or "",
            "database_summary": request.data.get("database_summary") or "",
            "nodes": nodes,
            "edges": edges,
        }

        try:
            validate_graph(graph)
        except TetherSchemaError as err:
            return Response(
                {"success": False, "error": f"Schema validation failed: {err}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        elapsed_ms: int | None = None
        if version.started_at is not None:
            elapsed_ms = int((now - version.started_at).total_seconds() * 1000)

        with transaction.atomic():
            version.graph_json = graph
            version.status = "success"
            version.completed_at = now
            if elapsed_ms is not None:
                version.execution_time_ms = elapsed_ms
            version.error_message = ""
            version.save()

            tether = version.tether
            tether.current_version = version
            tether.save(update_fields=["current_version", "updated_at"])

        return Response(
            {
                "success": True,
                "version_id": version.id,
                "nodes": len(nodes),
                "edges": len(edges),
            },
            status=status.HTTP_200_OK,
        )
