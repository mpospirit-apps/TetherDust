"""Tether admin API: CRUD + AI regeneration, status polling, and versions.

Ports ``management/views/tether.py`` + ``TetherForm``. The code side is exactly
one of a live ``Codebase`` or a codebase ``DocumentationSource`` (validated like
``Tether.clean``); the database side is a database ``DocumentationSource``.
Creating a tether — and the ``regenerate`` action — start a background
generation run on the active agent (``tether_engine.start_generation``); the
``status`` action exposes the live agent log for polling.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from engine.models import DocumentationSource, Tether, TetherVersion
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


def _version_dict(version: TetherVersion, *, is_current: bool) -> dict[str, Any]:
    return {
        "id": version.pk,
        "version_number": version.version_number,
        "status": version.status,
        "started_at": version.started_at.isoformat(),
        "completed_at": version.completed_at.isoformat() if version.completed_at else None,
        "execution_time_ms": version.execution_time_ms,
        "error_message": version.error_message,
        "agent_log_excerpt": version.agent_log_excerpt,
        "triggered_by": version.triggered_by.username if version.triggered_by else None,
        "is_current": is_current,
    }


class TetherSerializer(serializers.ModelSerializer[Tether]):
    source_name = serializers.CharField(read_only=True)
    database_name = serializers.CharField(source="database_doc_source.folder_name", read_only=True)
    current_status = serializers.CharField(source="current_version.status", read_only=True)
    latest_version = serializers.SerializerMethodField()

    class Meta(SerializerMeta):
        model = Tether
        fields = [
            "id",
            "name",
            "description",
            "codebase",
            "codebase_doc_source",
            "database_doc_source",
            "source_name",
            "database_name",
            "current_status",
            "latest_version",
            "is_active",
            "allowed_roles",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "source_name",
            "database_name",
            "current_status",
            "latest_version",
            "created_at",
            "updated_at",
        ]

    def get_latest_version(self, obj: Tether) -> dict[str, Any] | None:
        latest = TetherVersion.objects.filter(tether=obj).order_by("-version_number").first()
        if latest is None:
            return None
        return {
            "id": latest.pk,
            "version_number": latest.version_number,
            "status": latest.status,
            "started_at": latest.started_at.isoformat(),
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        codebase = attrs.get("codebase", getattr(self.instance, "codebase", None))
        codebase_doc = attrs.get(
            "codebase_doc_source", getattr(self.instance, "codebase_doc_source", None)
        )
        if bool(codebase) == bool(codebase_doc):
            raise serializers.ValidationError(
                {
                    "codebase": (
                        "Pick exactly one code source: a codebase repository or a codebase "
                        "documentation source."
                    )
                }
            )
        return attrs


class TetherViewSet(viewsets.ModelViewSet[Tether]):
    """Staff CRUD for tethers, plus regenerate / status / versions / sources."""

    permission_classes = [IsStaffUser]
    serializer_class = TetherSerializer

    def get_queryset(self) -> QuerySet[Tether]:
        return Tether.objects.select_related(
            "codebase", "codebase_doc_source", "database_doc_source", "current_version"
        ).order_by("name")

    def perform_create(self, serializer: Any) -> None:
        from engine.engines.tether_engine import start_generation

        tether = serializer.save(created_by=self.request.user)
        start_generation(tether, cast(User, self.request.user))

    @action(detail=True, methods=["post"])
    def regenerate(self, request: Request, pk: str | None = None) -> Response:
        from engine.engines.tether_engine import start_generation

        tether = self.get_object()
        version = start_generation(tether, cast(User, request.user))
        return Response(
            {"version_id": version.pk, "version_number": version.version_number},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def status(self, request: Request, pk: str | None = None) -> Response:
        """Polling endpoint: latest version status + live agent thoughts."""
        tether = self.get_object()
        latest = TetherVersion.objects.filter(tether=tether).order_by("-version_number").first()
        if latest is None:
            return Response({"status": "none"})
        return Response(
            {
                "status": latest.status,
                "version_number": latest.version_number,
                "version_id": latest.pk,
                "agent_output": latest.agent_log_excerpt,
                "error": latest.error_message,
                "execution_time_ms": latest.execution_time_ms,
                "is_current": tether.current_version_id == latest.pk,
            }
        )

    @action(detail=True, methods=["get"])
    def versions(self, request: Request, pk: str | None = None) -> Response:
        tether = self.get_object()
        versions = TetherVersion.objects.filter(tether=tether).select_related("triggered_by")
        return Response(
            {
                "versions": [
                    _version_dict(v, is_current=tether.current_version_id == v.pk) for v in versions
                ]
            }
        )

    @action(detail=False, methods=["get"])
    def sources(self, request: Request) -> Response:
        """Code + database source options for the tether form's dropdowns."""
        codebase_docs = DocumentationSource.objects.filter(
            doc_type=DocumentationSource.DocType.CODEBASE, is_active=True
        )
        database_docs = DocumentationSource.objects.filter(
            doc_type=DocumentationSource.DocType.DATABASE, is_active=True
        )
        from engine.models import Codebase

        return Response(
            {
                "codebases": [
                    {"id": c.pk, "name": c.name} for c in Codebase.objects.filter(is_active=True)
                ],
                "codebase_docs": [{"id": d.pk, "name": d.folder_name} for d in codebase_docs],
                "database_docs": [{"id": d.pk, "name": d.folder_name} for d in database_docs],
            }
        )
