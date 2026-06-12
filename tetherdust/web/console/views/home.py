"""Admin landing page with system metrics."""

from __future__ import annotations

from core.models import (
    AgentConfiguration,
    ChatSession,
    Codebase,
    DatabaseConnection,
    DocumentationSource,
    QueryAuditLog,
    Role,
    SystemConfiguration,
    Tether,
    ToolConfiguration,
)
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

TREND_DAYS = 14
SPARK_W = 100
SPARK_H = 30
SPARK_PAD = 3


def _sparkline_points(
    values: list[int], width: int = SPARK_W, height: int = SPARK_H, pad: int = SPARK_PAD
) -> str:
    """Build an SVG polyline `points` string for a small inline sparkline."""
    if not values:
        return ""
    mx = max(values) or 1
    n = len(values)
    span = height - 2 * pad
    step = width / (n - 1) if n > 1 else 0
    pts = []
    for i, v in enumerate(values):
        x = round(i * step, 2)
        y = round(height - pad - (v / mx) * span, 2)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def _delta(current: int, previous: int) -> dict[str, object]:
    """Return a {value, dir, pct} comparison badge dict, or None if no baseline."""
    diff = current - previous
    if previous == 0:
        pct = None if diff == 0 else 100
    else:
        pct = round(diff / previous * 100)
    direction = "flat" if diff == 0 else ("up" if diff > 0 else "down")
    return {"value": diff, "dir": direction, "pct": pct, "abs": abs(diff)}


def _daily_query_trend(now: timezone.datetime) -> list[dict[str, object]]:
    """Group the last TREND_DAYS of audit logs into ordered daily buckets."""
    start = (now - timezone.timedelta(days=TREND_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = (
        QueryAuditLog.objects.filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"), failed=Count("id", filter=Q(success=False)))
    )
    by_day = {r["day"]: r for r in rows}

    days = []
    today = timezone.localdate()
    for offset in range(TREND_DAYS - 1, -1, -1):
        d = today - timezone.timedelta(days=offset)
        row = by_day.get(d)
        total = row["total"] if row else 0
        failed = row["failed"] if row else 0
        days.append({"date": d, "total": total, "failed": failed, "ok": total - failed})

    max_total = max((d["total"] for d in days), default=0) or 1
    for d in days:
        d["ok_h"] = round(d["ok"] / max_total * 100, 2)
        d["failed_h"] = round(d["failed"] / max_total * 100, 2)
    return days


@staff_member_required(login_url="/login/")
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Admin dashboard with system metrics, trends, and health."""
    now = timezone.now()
    last_24h = now - timezone.timedelta(hours=24)
    prev_24h = now - timezone.timedelta(hours=48)
    last_7d = now - timezone.timedelta(days=7)

    queries_24h = QueryAuditLog.objects.filter(created_at__gte=last_24h).count()
    failed_24h = QueryAuditLog.objects.filter(created_at__gte=last_24h, success=False).count()
    queries_prev = QueryAuditLog.objects.filter(
        created_at__gte=prev_24h, created_at__lt=last_24h
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

    trend = _daily_query_trend(now)
    kpis = {
        "queries": {
            "delta": _delta(queries_24h, queries_prev),
            "spark": _sparkline_points([d["total"] for d in trend]),  # type: ignore[misc]
        },
        "sessions": {"delta": _delta(sessions_24h, sessions_prev)},
        "failed": {
            "delta": _delta(
                failed_24h,
                QueryAuditLog.objects.filter(
                    created_at__gte=prev_24h, created_at__lt=last_24h, success=False
                ).count(),
            )
        },
    }

    top_databases = list(
        QueryAuditLog.objects.filter(created_at__gte=last_7d, database__isnull=False)
        .values("database__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )
    max_db = top_databases[0]["count"] if top_databases else 1
    for row in top_databases:
        row["pct"] = round(row["count"] / max_db * 100, 1)

    agent = AgentConfiguration.get_active()
    if agent is None:
        health: dict[str, object] = {
            "status": "setup",
            "label": "Needs setup",
            "detail": "No active AI agent configured.",
        }
    elif queries_24h and success_rate < 90:
        noun = "query" if failed_24h == 1 else "queries"
        health = {
            "status": "degraded",
            "label": "Degraded",
            "detail": f"{failed_24h} failed {noun} in the last 24h.",
        }
    else:
        health = {"status": "operational", "label": "Operational", "detail": "All systems nominal."}
    health["agent"] = agent

    recent_queries = QueryAuditLog.objects.select_related("user", "database").order_by(
        "-created_at"
    )[:8]
    recent_sessions = ChatSession.objects.select_related("user").order_by("-updated_at")[:8]

    return render(
        request,
        "console/dashboard.html",
        {
            "metrics": metrics,
            "kpis": kpis,
            "trend": trend,
            "top_databases": top_databases,
            "health": health,
            "recent_queries": recent_queries,
            "recent_sessions": recent_sessions,
            "now": now,
            "section": "dashboard",
        },
    )


def _quickstart_steps():
    """Build the ordered onboarding checklist with completion derived from state."""
    db_connected = DatabaseConnection.objects.exists()
    db_documented = DocumentationSource.objects.filter(
        doc_type=DocumentationSource.DocType.DATABASE,
        is_active=True,
    ).exists()
    repo_connected = Codebase.objects.exists()
    repo_documented = DocumentationSource.objects.filter(
        doc_type=DocumentationSource.DocType.CODEBASE,
        is_active=True,
    ).exists()

    steps = [
        {
            "title": "Configure an AI agent",
            "description": "Set up and activate an agent to handle chat queries.",
            "done": AgentConfiguration.get_active() is not None,
            "cta_url": "console:agent_add",
            "cta_label": "Configure agent",
        },
        {
            "title": "Connect a database and document it",
            "description": "Give agents a database to query, then generate its documentation.",
            "substeps": [
                {
                    "title": "Connect a database",
                    "done": db_connected,
                    "cta_url": "console:database_add",
                    "cta_label": "Connect database",
                },
                {
                    "title": "Create database documentation",
                    "done": db_documented,
                    "cta_url": "console:docsource_generate_page",
                    "cta_label": "Generate docs",
                },
            ],
        },
        {
            "title": "Connect a repository and document it",
            "description": "Link a codebase, then generate its documentation.",
            "substeps": [
                {
                    "title": "Connect a repository",
                    "done": repo_connected,
                    "cta_url": "console:codebase_add",
                    "cta_label": "Connect repository",
                },
                {
                    "title": "Create codebase documentation",
                    "done": repo_documented,
                    "cta_url": "console:docsource_generate_page",
                    "cta_label": "Generate docs",
                },
            ],
        },
        {
            "title": "Create a Tether",
            "description": "Visually link your codebase and database documentation.",
            "done": Tether.objects.exists(),
            "cta_url": "console:tether_add",
            "cta_label": "Create Tether",
        },
        {
            "title": "Explore dashboards & reports",
            "description": "Build AI-generated dashboards and schedule reports, then finish.",
            "done": SystemConfiguration.get_value("onboarding_finished", False),
            "is_finish": True,
        },
    ]

    for step in steps:
        if "substeps" in step:
            step["done"] = all(sub["done"] for sub in step["substeps"])

    return steps


@staff_member_required(login_url="/login/")
def quickstart_view(request):
    """Onboarding checklist tab with per-step completion and CTAs."""
    steps = _quickstart_steps()
    return render(
        request,
        "console/quickstart.html",
        {
            "steps": steps,
            "completed_count": sum(1 for s in steps if s["done"]),
            "total": len(steps),
            "section": "quickstart",
        },
    )


@staff_member_required(login_url="/login/")
@require_POST
def quickstart_finish_view(request):
    """Mark the informational final onboarding step as acknowledged."""
    SystemConfiguration.set_value(
        "onboarding_finished",
        True,
        value_type="boolean",
        description="Admin acknowledged the final onboarding step.",
    )
    return redirect("console:quickstart")
