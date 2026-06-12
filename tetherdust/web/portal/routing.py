"""WebSocket URL routing for the portal app."""

from django.urls import re_path

from .consumers.chat import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<session_id>\w+)/$", ChatConsumer.as_asgi()),
    re_path(r"ws/chat/$", ChatConsumer.as_asgi()),
]
