"""URL configuration for the TetherDust backend.

API-only backend: the React SPA (served by nginx) is the entire UI, so the HTTP
surface is the DRF API under ``/api/`` plus the root liveness/readiness probes
(``/healthz``, ``/readyz``) the container healthcheck hits. WhiteNoise serves the
backend's own static assets (the DRF browsable API); the WebSocket layer is
mounted separately in ``project/asgi.py``.
"""

from api.health import healthz_view, readyz_view
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("healthz", healthz_view),
    path("readyz", readyz_view),
    path("api/", include("api.urls")),
]
