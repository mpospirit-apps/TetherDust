"""WebSocket URL routing for the console (mission-control) app."""

from django.urls import re_path

from .consumers.chart_edit import ChartEditConsumer

websocket_urlpatterns = [
    re_path(r"ws/chart-edit/(?P<chart_id>\d+)/$", ChartEditConsumer.as_asgi()),
]
