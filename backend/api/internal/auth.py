"""Shared-secret authentication for the internal service API.

Mirrors the ``X-Gateway-Secret`` / ``X-MCP-Filter-Secret`` handshake used
elsewhere, but for inbound calls (tdmcp → backend). The token travels in the
``X-Service-Token`` header and is compared against ``INTERNAL_API_SERVICE_TOKEN``.

Fails **closed**: when the token is unset on the server, every internal call is
rejected (this is a write API, so an unconfigured secret must not silently open
it up). Session auth is intentionally not consulted here — these endpoints are
service-to-service only and never carry a session cookie or CSRF token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework import authentication, exceptions
from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

SERVICE_TOKEN_HEADER = "X-Service-Token"


class ServicePrincipal:
    """Lightweight authenticated principal for service-token callers.

    Not a Django user — it only needs the attributes DRF's permission layer
    reads. It deliberately has no staff/superuser privileges.
    """

    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    is_anonymous = False

    def __str__(self) -> str:
        return "internal-service"


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate a request by a matching ``X-Service-Token`` header."""

    def authenticate(self, request: Request) -> tuple[ServicePrincipal, str] | None:
        token = request.headers.get(SERVICE_TOKEN_HEADER, "")
        if not token:
            return None  # no token → fall through to AnonymousUser → 403
        expected = getattr(settings, "INTERNAL_API_SERVICE_TOKEN", "")
        if not expected:
            raise exceptions.AuthenticationFailed(
                "Internal API service token is not configured on the server."
            )
        if not constant_time_compare(token, expected):
            raise exceptions.AuthenticationFailed("Invalid service token.")
        return (ServicePrincipal(), token)


class IsServiceToken(BasePermission):
    """Allow only requests authenticated by :class:`ServiceTokenAuthentication`."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(getattr(request, "user", None), ServicePrincipal)
