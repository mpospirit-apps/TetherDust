"""Liveness/readiness probes — plain Django views (no DRF, no auth).

Mounted at the root (``/healthz``, ``/readyz``) in ``project/urls.py`` so the
container healthcheck and orchestrators can reach them without the ``/api/``
prefix. Ported verbatim from the legacy ``workspace/views/api.py`` when the
backend went API-only.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz_view(request: HttpRequest) -> JsonResponse:
    """Liveness probe — returns 200 if the process is running."""
    return JsonResponse({"status": "ok"})


def readyz_view(request: HttpRequest) -> JsonResponse:
    """Readiness probe — checks Django DB and configured database connections."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        connection.ensure_connection()
        checks["django_db"] = "ok"
    except Exception as e:
        checks["django_db"] = str(e)
        healthy = False

    try:
        from engine.engines.db_runner import ping
        from engine.models import DatabaseConnection

        active_dbs = DatabaseConnection.objects.filter(is_active=True)
        for db in active_dbs:
            try:
                ping(db)
                checks[f"db:{db.name}"] = "ok"
            except Exception as e:
                checks[f"db:{db.name}"] = str(e)
                healthy = False
    except Exception as e:
        checks["configured_dbs"] = f"check failed: {e}"

    status_code = 200 if healthy else 503
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks}, status=status_code
    )
