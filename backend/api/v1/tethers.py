"""Public tethers API — role-scoped list/detail + the rendered graph JSON.

Replaces ``workspace/views/tethers.py``. The graph endpoint returns the current
version's stored ``graph_json`` (the SPA canvas renders it); when no successful
version exists yet it returns an empty pending graph so the viewer can poll.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from engine.models import Tether
from engine.services import PermissionService, TetherService, get
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewTethers

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db.models import QuerySet


def _allowed_tethers(user: AbstractUser) -> QuerySet[Tether]:
    """Tethers the user may see (staff → all active; else role-allowed)."""
    if user.is_staff:
        return Tether.objects.filter(is_active=True).select_related(
            "current_version", "codebase", "codebase_doc_source", "database_doc_source"
        )
    profile = getattr(user, "profile", None)
    if not profile:
        return Tether.objects.none()
    return (
        get(PermissionService)
        .get_allowed_tethers(profile)
        .select_related("current_version", "codebase", "codebase_doc_source", "database_doc_source")
    )


def _tether_summary(tether: Tether) -> dict[str, object]:
    return {
        "id": tether.pk,
        "name": tether.name,
        "description": tether.description,
        "source_name": get(TetherService).source_name(tether),
        "database_name": tether.database_doc_source.folder_name,
        "has_graph": (
            tether.current_version is not None and tether.current_version.status == "success"
        ),
    }


class TethersView(APIView):
    """Role-scoped tether list."""

    permission_classes = [CanViewTethers]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        tethers = _allowed_tethers(user).order_by("name")
        return Response({"tethers": [_tether_summary(t) for t in tethers]})


class TetherDetailView(APIView):
    """A single tether's metadata (role-checked)."""

    permission_classes = [CanViewTethers]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        tether = _allowed_tethers(user).filter(pk=pk).first()
        if tether is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        version = tether.current_version
        return Response(
            {
                **_tether_summary(tether),
                "status": version.status if version else None,
            }
        )


class TetherGraphView(APIView):
    """The current version's graph JSON (role-checked)."""

    permission_classes = [CanViewTethers]

    def get(self, request: Request, pk: str) -> Response:
        user = cast("AbstractUser", request.user)
        tether = _allowed_tethers(user).filter(pk=pk).first()
        if tether is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if tether.current_version is None:
            return Response({"nodes": [], "edges": [], "schema_version": 1, "status": "pending"})
        return Response(tether.current_version.graph_json or {"nodes": [], "edges": []})
