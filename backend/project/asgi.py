"""
ASGI config for tetherdust_web project.

It exposes the ASGI callable as a module-level variable named ``application``.
Includes WebSocket routing for Django Channels.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

# Initialize Django ASGI application early to ensure models are loaded
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from management.routing import websocket_urlpatterns as management_ws  # noqa: E402
from workspace.routing import websocket_urlpatterns as workspace_ws  # noqa: E402

websocket_urlpatterns = workspace_ws + management_ws

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
