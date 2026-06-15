"""Template context processors for the public portal."""

from typing import TYPE_CHECKING, cast

from core.models import Dashboard, DocumentationSource, ReportDefinition, Tether, UserProfile
from django.http import HttpRequest

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def docs_access(request: HttpRequest) -> dict[str, object]:
    """Add can_view_docs flag to every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"can_view_docs": False}

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        return {"can_view_docs": DocumentationSource.objects.filter(is_active=True).exists()}

    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return {"can_view_docs": False}

    return {"can_view_docs": profile.can_view_docs}


def reports_access(request: HttpRequest) -> dict[str, object]:
    """Add can_view_reports flag to every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"can_view_reports": False}

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        return {"can_view_reports": ReportDefinition.objects.filter(is_active=True).exists()}

    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return {"can_view_reports": False}

    return {"can_view_reports": profile.can_view_reports}


def dashboards_access(request: HttpRequest) -> dict[str, object]:
    """Add can_view_dashboards flag to every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"can_view_dashboards": False}

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        return {"can_view_dashboards": Dashboard.objects.filter(is_active=True).exists()}

    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return {"can_view_dashboards": False}

    return {"can_view_dashboards": profile.can_view_dashboards}


def chat_access(request: HttpRequest) -> dict[str, object]:
    """Add can_chat flag to every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"can_chat": False}

    user = cast("AbstractUser", request.user)
    if user.is_staff:
        return {"can_chat": True}

    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return {"can_chat": False}

    return {"can_chat": profile.can_chat}


def tethers_access(request: HttpRequest) -> dict[str, object]:
    """Add can_view_tethers flag to every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"can_view_tethers": False}

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        return {"can_view_tethers": Tether.objects.filter(is_active=True).exists()}

    try:
        profile = getattr(user, "profile")
    except UserProfile.DoesNotExist:
        return {"can_view_tethers": False}

    return {"can_view_tethers": profile.can_view_tethers}
