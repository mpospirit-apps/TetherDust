"""Template context processors for the mission-control console."""

from core.models import UserProfile
from core.version import update_available
from django.http import HttpRequest


def user_management_access(request: HttpRequest) -> dict[str, object]:
    """Add can_manage_users flag to every template context."""
    if (
        not hasattr(request, "user")
        or not request.user.is_authenticated
        or not request.user.is_staff
    ):
        return {"can_manage_users": False}
    if request.user.is_superuser:
        return {"can_manage_users": True}
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return {"can_manage_users": False}
    return {"can_manage_users": bool(profile.role and profile.role.can_manage_users)}


def update_status(request: HttpRequest) -> dict[str, object]:
    """Expose ``update_available`` to staff templates so the sidebar can badge
    the Version tab. Computed from the cached release tag — no network call."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_staff:
        return {"update_available": False}
    try:
        return {"update_available": update_available()}
    except Exception:
        # Never let a version-check hiccup break page rendering.
        return {"update_available": False}
