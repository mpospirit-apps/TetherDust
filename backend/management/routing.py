"""WebSocket URL routing for the management (mission-control) app."""

from typing import Any, cast

from django.urls import re_path

from .consumers.chart_edit import ChartEditConsumer

websocket_urlpatterns = [
    # Chart IDs are prefixed strings (cht_…), not integers.
    re_path(r"ws/chart-edit/(?P<chart_id>[^/]+)/$", cast(Any, ChartEditConsumer.as_asgi())),
]
