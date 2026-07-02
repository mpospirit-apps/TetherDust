"""Admin overview ("Mission Control") metrics API.

Ports the legacy server-rendered ``dashboard_view`` (``management/views/home.py``):
system inventory counts, 24h KPIs with deltas, a 14-day query-volume trend, top
databases, health status, and recent-activity feeds. Presentation geometry
(sparkline points, bar heights, percentages) is computed client-side; this
endpoint returns the raw numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from engine.models import (
    ChatSession,
    DatabaseConnection,
    DocumentationSource,
    QueryAuditLog,
    Role,
    Tether,
    ToolConfiguration,
)
from engine.services import AgentService, get
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsStaffUser

TREND_DAYS = 14


def _delta(current: int, previous: int) -> dict[str, Any]:
    """A {value, dir, pct} comparison badge vs a prior period (``pct`` may be null)."""
    diff = current - previous
    if previous == 0:
        pct = None if diff == 0 else 100
    else:
        pct = round(diff / previous * 100)
    direction = "flat" if diff == 0 else ("up" if diff > 0 else "down")
    return {"value": diff, "dir": direction, "pct": pct}


def _daily_query_trend(now: datetime) -> list[dict[str, Any]]:
    """Group the last ``TREND_DAYS`` of audit logs into ordered daily buckets."""
    start = (now - timedelta(days=TREND_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = (
        QueryAuditLog.objects.filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"), failed=Count("id", filter=Q(success=False)))
    )
    by_day = {r["day"]: r for r in rows}

    days: list[dict[str, Any]] = []
    today = timezone.localdate()
    for offset in range(TREND_DAYS - 1, -1, -1):
        d = today - timedelta(days=offset)
        row = by_day.get(d)
        total = row["total"] if row else 0
        failed = row["failed"] if row else 0
        days.append({"date": d.isoformat(), "total": total, "failed": failed, "ok": total - failed})
    return days


class OverviewView(APIView):
    """Mission Control metrics for the admin landing page."""

    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        prev_24h = now - timedelta(hours=48)
        last_7d = now - timedelta(days=7)

        queries_24h = QueryAuditLog.objects.filter(created_at__gte=last_24h).count()
        failed_24h = QueryAuditLog.objects.filter(created_at__gte=last_24h, success=False).count()
        queries_prev = QueryAuditLog.objects.filter(
            created_at__gte=prev_24h, created_at__lt=last_24h
        ).count()
        failed_prev = QueryAuditLog.objects.filter(
            created_at__gte=prev_24h, created_at__lt=last_24h, success=False
        ).count()
        sessions_24h = ChatSession.objects.filter(updated_at__gte=last_24h).count()
        sessions_prev = ChatSession.objects.filter(
            updated_at__gte=prev_24h, updated_at__lt=last_24h
        ).count()

        ok_24h = queries_24h - failed_24h
        success_rate = round(ok_24h / queries_24h * 100) if queries_24h else 100

        metrics = {
            "active_databases": DatabaseConnection.objects.filter(is_active=True).count(),
            "total_databases": DatabaseConnection.objects.count(),
            "active_tools": ToolConfiguration.objects.filter(
                is_enabled=True, mcp_server__is_active=True
            ).count(),
            "total_tools": ToolConfiguration.objects.count(),
            "total_users": User.objects.filter(is_active=True).count(),
            "total_roles": Role.objects.filter(is_active=True).count(),
            "doc_sources": DocumentationSource.objects.filter(is_active=True).count(),
            "tethers": Tether.objects.count(),
            "queries_24h": queries_24h,
            "failed_queries_24h": failed_24h,
            "active_sessions": sessions_24h,
            "success_rate": success_rate,
        }

        kpis = {
            "queries": {"delta": _delta(queries_24h, queries_prev)},
            "sessions": {"delta": _delta(sessions_24h, sessions_prev)},
            "failed": {"delta": _delta(failed_24h, failed_prev)},
        }

        top_databases = [
            {"name": row["database__name"], "count": row["count"]}
            for row in QueryAuditLog.objects.filter(created_at__gte=last_7d, database__isnull=False)
            .values("database__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        ]

        agent = get(AgentService).get_active()
        if agent is None:
            health: dict[str, Any] = {
                "status": "setup",
                "label": "Needs setup",
                "detail": "No active AI agent configured.",
                "agent": None,
            }
        else:
            agent_info = {"name": agent.name, "type": agent.get_agent_type_display()}
            if queries_24h and success_rate < 90:
                noun = "query" if failed_24h == 1 else "queries"
                health = {
                    "status": "degraded",
                    "label": "Degraded",
                    "detail": f"{failed_24h} failed {noun} in the last 24h.",
                    "agent": agent_info,
                }
            else:
                health = {
                    "status": "operational",
                    "label": "Operational",
                    "detail": "All systems nominal.",
                    "agent": agent_info,
                }

        recent_queries = [
            {
                "id": log.id,
                "user": log.user.username if log.user else None,
                "database": log.database.name if log.database else None,
                "success": log.success,
                "row_count": log.row_count,
                "execution_time_ms": log.execution_time_ms,
                "created_at": log.created_at.isoformat(),
            }
            for log in QueryAuditLog.objects.select_related("user", "database").order_by(
                "-created_at"
            )[:8]
        ]
        recent_sessions = [
            {
                "id": r["id"],
                "title": r["title"],
                "user": r["user__username"],
                "message_count": r["message_count"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in ChatSession.objects.annotate(message_count=Count("messages"))
            .order_by("-updated_at")
            .values("id", "title", "updated_at", "user__username", "message_count")[:8]
        ]

        return Response(
            {
                "metrics": metrics,
                "kpis": kpis,
                "trend": _daily_query_trend(now),
                "top_databases": top_databases,
                "health": health,
                "recent_queries": recent_queries,
                "recent_sessions": recent_sessions,
                "generated_at": now.isoformat(),
            }
        )
