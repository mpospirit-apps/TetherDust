"""DRF permission classes wrapping the engine ``PermissionService``.

These guard API endpoints with the same per-capability checks the SPA's
``/auth/me`` payload exposes. Staff are always allowed; non-staff are delegated
to ``PermissionService`` via their ``UserProfile``. Object-level / queryset
scoping for role-restricted resources (allowed dashboards/reports/tethers/doc
sources) is applied in the viewsets, not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from engine.models import UserProfile
from engine.services import PermissionService, get
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class IsStaffUser(BasePermission):
    """Allow only authenticated staff users (admin-console endpoints)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast("AbstractUser", request.user)
        return bool(user.is_authenticated and user.is_staff)


class _ProfilePermission(BasePermission):
    """Base: staff always pass; non-staff delegate to a per-capability check."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast("AbstractUser", request.user)
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        try:
            profile = getattr(user, "profile")
        except UserProfile.DoesNotExist:
            return False
        return self._check(profile)

    def _check(self, profile: UserProfile) -> bool:
        raise NotImplementedError


class CanChat(_ProfilePermission):
    def _check(self, profile: UserProfile) -> bool:
        return get(PermissionService).can_chat(profile)


class CanViewDocs(_ProfilePermission):
    def _check(self, profile: UserProfile) -> bool:
        return get(PermissionService).can_view_docs(profile)


class CanViewReports(_ProfilePermission):
    def _check(self, profile: UserProfile) -> bool:
        return get(PermissionService).can_view_reports(profile)


class CanViewDashboards(_ProfilePermission):
    def _check(self, profile: UserProfile) -> bool:
        return get(PermissionService).can_view_dashboards(profile)


class CanViewTethers(_ProfilePermission):
    def _check(self, profile: UserProfile) -> bool:
        return get(PermissionService).can_view_tethers(profile)


class CanManageUsers(BasePermission):
    """Superusers always; otherwise staff whose role has ``can_manage_users``."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast("AbstractUser", request.user)
        if not user.is_authenticated or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        try:
            profile = getattr(user, "profile")
        except UserProfile.DoesNotExist:
            return False
        return bool(profile.role and profile.role.can_manage_users)
