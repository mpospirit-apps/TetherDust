"""Documentation source admin API: CRUD + validate + AI generation.

Ports ``management/views/docsource.py``. Sources map to top-level folders under
``documentations/`` (auto-discovered via ``DocSourceService.sync_from_filesystem``).
Generation (single-file + multi-file library) is delegated to
``engine.engines.docgen`` and tracked by ``DocGenerationLog``, which the SPA polls
via the ``status`` action.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.contrib.auth.models import User
from engine.engines import docgen
from engine.models import (
    DOC_TYPE_DESCRIPTIONS,
    AgentConfiguration,
    Codebase,
    DatabaseConnection,
    DocGenerationLog,
    DocumentationSource,
)
from engine.services import DocSourceService, get
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


class DocSourceSerializer(serializers.ModelSerializer[DocumentationSource]):
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)

    class Meta(SerializerMeta):
        model = DocumentationSource
        fields = [
            "id",
            "folder_name",
            "doc_type",
            "doc_type_display",
            "description",
            "file_patterns",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_folder_name(self, value: str) -> str:
        path = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / value
        if not path.exists() or not path.is_dir():
            raise serializers.ValidationError(f"Folder does not exist: {value}")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        folder_name = attrs.get("folder_name") or getattr(self.instance, "folder_name", None)
        file_patterns = attrs.get(
            "file_patterns", getattr(self.instance, "file_patterns", None)
        ) or ["*.md"]
        if folder_name:
            path = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / folder_name
            if path.exists() and path.is_dir():
                file_count = sum(len(list(path.rglob(p))) for p in file_patterns)
                if file_count == 0:
                    raise serializers.ValidationError(
                        {
                            "file_patterns": f"No files matching {file_patterns} found in "
                            f'"{folder_name}".'
                        }
                    )
        return attrs


def _resolve_names(model: Any, field: str, ids: list[str]) -> list[str]:
    return list(model.objects.filter(pk__in=ids, is_active=True).values_list(field, flat=True))


class DocSourceViewSet(viewsets.ModelViewSet[DocumentationSource]):
    """Staff CRUD for documentation sources, plus validate + AI generation."""

    permission_classes = [IsStaffUser]
    serializer_class = DocSourceSerializer
    queryset = DocumentationSource.objects.all()

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Discover folders added on disk before listing (mirrors the legacy view).
        get(DocSourceService).sync_from_filesystem()
        return super().list(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        obj = self.get_object()
        # Remove the folder on disk too, else the next list() sync would rediscover
        # the orphaned folder and recreate the source. Guard the path so we only
        # ever remove a directory directly under the documentations dir.
        docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR).resolve()
        folder = Path(get(DocSourceService).resolved_path(obj)).resolve()
        if folder != docs_dir and docs_dir in folder.parents and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def validate(self, request: Request, pk: str | None = None) -> Response:
        """Check the source folder resolves and matches files (mirrors the badge)."""
        obj = self.get_object()
        path = Path(get(DocSourceService).resolved_path(obj))
        if not path.exists():
            return Response({"ok": False, "level": "error", "message": "Folder not found"})
        if not path.is_dir():
            return Response({"ok": False, "level": "error", "message": "Not a directory"})

        patterns = obj.file_patterns or ["*.md"]
        all_files = [f for p in patterns for f in path.rglob(p) if f.is_file()]
        if not all_files:
            return Response({"ok": False, "level": "warning", "message": "No matching files"})

        latest_mtime = max(f.stat().st_mtime for f in all_files)
        last_mod = datetime.datetime.fromtimestamp(latest_mtime).strftime("%b %d, %H:%M")
        return Response(
            {
                "ok": True,
                "level": "success",
                "file_count": len(all_files),
                "last_modified": last_mod,
                "message": f"{len(all_files)} files",
            }
        )

    @action(detail=False, methods=["get"])
    def folders(self, request: Request) -> Response:
        """Top-level folders under documentations/ (for the register dropdown)."""
        registered = set(DocumentationSource.objects.values_list("folder_name", flat=True))
        return Response(
            {
                "folders": [
                    {"name": name, "registered": name in registered}
                    for name in docgen.top_level_folders()
                ]
            }
        )

    @action(detail=False, methods=["get"], url_path="generate-options")
    def generate_options(self, request: Request) -> Response:
        """Source/agent/destination options for the AI generation forms."""
        return Response(
            {
                "databases": [
                    {"id": d.pk, "name": d.name}
                    for d in DatabaseConnection.objects.filter(is_active=True)
                ],
                "doc_sources": [
                    {"id": s.pk, "name": s.folder_name}
                    for s in DocumentationSource.objects.filter(is_active=True)
                ],
                "codebases": [
                    {"id": c.pk, "name": c.name} for c in Codebase.objects.filter(is_active=True)
                ],
                "agents": [
                    {"id": a.pk, "name": a.name, "is_active": a.is_active}
                    for a in AgentConfiguration.objects.all()
                ],
                "dest_folders": docgen.nested_folders(),
                "top_folders": docgen.top_level_folders(),
                "doc_types": [
                    {
                        "value": value,
                        "label": label,
                        "description": DOC_TYPE_DESCRIPTIONS.get(value, ""),
                    }
                    for value, label in DocumentationSource.DocType.choices
                ],
                "library_doc_types": [
                    {"value": value, "label": label}
                    for value, label in DocumentationSource.DocType.choices
                    if value in docgen.LIBRARY_DOC_TYPES
                ],
            }
        )

    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        """Start single-file AI documentation generation; returns the log id."""
        data = request.data
        doc_name = (data.get("doc_name") or "").strip()
        doc_type = data.get("doc_type")
        agent_id = data.get("agent")
        destination = (data.get("destination") or "").strip()
        scope = (data.get("scope") or "").strip()

        if not all([doc_name, doc_type, agent_id, destination]):
            return Response(
                {"detail": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST
            )
        doc_type = str(doc_type)

        destination = destination.replace("\\", "/")
        destination = "/".join(p for p in destination.split("/") if p and p != "..")
        if not destination:
            return Response(
                {"detail": "Invalid destination folder name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agent_config = AgentConfiguration.objects.filter(pk=agent_id).first()
        if agent_config is None:
            return Response({"detail": "Agent not found."}, status=status.HTTP_404_NOT_FOUND)

        log = docgen.start_single(
            user=cast(User, request.user),
            agent_config=agent_config,
            doc_name=doc_name,
            doc_type=doc_type,
            destination=destination,
            scope=scope,
            db_names=_resolve_names(DatabaseConnection, "name", data.get("source_db", [])),
            doc_names=_resolve_names(
                DocumentationSource, "folder_name", data.get("source_doc", [])
            ),
            codebase_names=_resolve_names(Codebase, "name", data.get("source_codebase", [])),
        )
        return Response({"log_id": log.pk}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="generate-library")
    def generate_library(self, request: Request) -> Response:
        """Start multi-file AI documentation library generation; returns the log id."""
        data = request.data
        library_name = (data.get("library_name") or "").strip()
        agent_id = data.get("agent")
        source_doc_type = data.get("source_doc_type", DocumentationSource.DocType.DATABASE)
        if source_doc_type not in docgen.LIBRARY_DOC_TYPES:
            source_doc_type = DocumentationSource.DocType.DATABASE

        if not all([library_name, agent_id]):
            return Response(
                {"detail": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST
            )

        library_root = library_name.replace("\\", "/")
        library_root = "/".join(p for p in library_root.split("/") if p and p != "..")
        if not library_root:
            return Response({"detail": "Invalid library name."}, status=status.HTTP_400_BAD_REQUEST)

        agent_config = AgentConfiguration.objects.filter(pk=agent_id).first()
        if agent_config is None:
            return Response({"detail": "Agent not found."}, status=status.HTTP_404_NOT_FOUND)

        log = docgen.start_library(
            user=cast(User, request.user),
            agent_config=agent_config,
            library_root=library_root,
            source_doc_type=source_doc_type,
            db_names=_resolve_names(DatabaseConnection, "name", data.get("source_db", [])),
            doc_names=_resolve_names(
                DocumentationSource, "folder_name", data.get("source_doc", [])
            ),
            codebase_names=_resolve_names(Codebase, "name", data.get("source_codebase", [])),
        )
        return Response({"log_id": log.pk}, status=status.HTTP_202_ACCEPTED)


class DocGenerationLogSerializer(serializers.ModelSerializer[DocGenerationLog]):
    user = serializers.CharField(source="user.username", read_only=True, default=None)
    agent = serializers.CharField(source="agent.name", read_only=True, default=None)

    class Meta(SerializerMeta):
        model = DocGenerationLog
        fields = [
            "id",
            "status",
            "destination",
            "filename",
            "doc_type",
            "is_library",
            "execution_time_ms",
            "file_size",
            "error_message",
            "user",
            "agent",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class DocGenerationLogDetailSerializer(serializers.ModelSerializer[DocGenerationLog]):
    """Full record for the detail page — adds sources, structured errors, prompt, output."""

    user = serializers.CharField(source="user.username", read_only=True, default=None)
    agent = serializers.CharField(source="agent.name", read_only=True, default=None)

    class Meta(SerializerMeta):
        model = DocGenerationLog
        fields = [
            "id",
            "status",
            "destination",
            "filename",
            "doc_type",
            "is_library",
            "execution_time_ms",
            "file_size",
            "error_message",
            "errors",
            "source_databases",
            "source_docs",
            "prompt_used",
            "agent_output",
            "user",
            "agent",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class DocGenerationLogViewSet(viewsets.ReadOnlyModelViewSet[DocGenerationLog]):
    """Read-only docgen run history + a rich ``status`` payload for polling.

    ``list`` uses the lean serializer; ``retrieve`` returns the full record
    (prompt + agent output can be large, so they're detail-only).
    """

    permission_classes = [IsStaffUser]
    serializer_class = DocGenerationLogSerializer
    queryset = DocGenerationLog.objects.select_related("user", "agent").all()

    def get_serializer_class(self) -> type[serializers.BaseSerializer[DocGenerationLog]]:
        if self.action == "retrieve":
            return DocGenerationLogDetailSerializer
        return DocGenerationLogSerializer

    @action(detail=True, methods=["get"])
    def status(self, request: Request, pk: str | None = None) -> Response:
        return Response(docgen.status_payload(self.get_object()))
