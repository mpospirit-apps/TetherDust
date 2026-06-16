"""WebSocket URL routing for the workspace app."""

from typing import Any, cast

from django.urls import re_path

from .consumers.chat import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<session_id>\w+)/$", cast(Any, ChatConsumer.as_asgi())),
    re_path(r"ws/chat/$", cast(Any, ChatConsumer.as_asgi())),
]
