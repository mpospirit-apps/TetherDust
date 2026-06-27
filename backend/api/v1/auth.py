"""Session-auth API endpoints for the SPA: csrf, login, logout, me.

Auth stays session-cookie based (Django ``login``/``logout``); the SPA obtains a
CSRF cookie from :class:`CsrfView` and echoes it back in the ``X-CSRFToken``
header on unsafe requests. ``/auth/me`` returns the per-user capability flags
that the legacy template context processors used to inject.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from engine.models import (
    Dashboard,
    DocumentationSource,
    ReportDefinition,
    Tether,
    UserProfile,
)
from engine.services import PermissionService, get
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def access_flags(user: AbstractUser) -> dict[str, bool]:
    """Per-user UI capability flags, mirroring the legacy context processors."""
    flags = {
        "can_chat": False,
        "can_view_docs": False,
        "can_view_reports": False,
        "can_view_dashboards": False,
        "can_view_tethers": False,
    }
    if user.is_staff:
        flags["can_chat"] = True
        flags["can_view_docs"] = DocumentationSource.objects.filter(is_active=True).exists()
        flags["can_view_reports"] = ReportDefinition.objects.filter(is_active=True).exists()
        flags["can_view_dashboards"] = Dashboard.objects.filter(is_active=True).exists()
        flags["can_view_tethers"] = Tether.objects.filter(is_active=True).exists()
        return flags
    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return flags
    perms = get(PermissionService)
    flags["can_chat"] = perms.can_chat(profile)
    flags["can_view_docs"] = perms.can_view_docs(profile)
    flags["can_view_reports"] = perms.can_view_reports(profile)
    flags["can_view_dashboards"] = perms.can_view_dashboards(profile)
    flags["can_view_tethers"] = perms.can_view_tethers(profile)
    return flags


def user_payload(user: AbstractUser) -> dict[str, Any]:
    """Serialize the authenticated user, role, and capability flags for the SPA."""
    role: dict[str, Any] | None = None
    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        profile = None
    if profile is not None and profile.role is not None:
        role = {
            "id": profile.role.id,
            "name": profile.role.name,
            "is_admin_role": profile.role.is_admin_role,
        }
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "role": role,
        "permissions": access_flags(user),
    }


class CsrfView(APIView):
    """GET to obtain a CSRF cookie before the first unsafe request."""

    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request: Request) -> Response:
        return Response({"detail": "CSRF cookie set"})


class LoginView(APIView):
    """Session login. Sets the session cookie on success.

    ``ModelBackend`` already rejects inactive users, so a non-None result is a
    valid, active user.
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request._request, user)
        return Response(user_payload(cast("AbstractUser", user)))


class LogoutView(APIView):
    """Log the current session out."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Return the current user, role, and capability flags."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(user_payload(cast("AbstractUser", request.user)))
