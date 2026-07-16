"""Codebase admin API: CRUD + on-demand sync.

Ports ``management/views/codebase.py`` + the ``CodebaseForm``. The access token
is a write-only ``EncryptedCharField`` (blank on update keeps the stored token);
``repo_url`` is validated to an owner/repo pair for remote providers. ``local``
codebases instead point at a folder under ``sources/codebases/`` (``local_root``).
Saving (and an explicit ``sync``) enqueues the Celery ``sync_codebase`` task,
which caches the repo file tree for remote codebases and refreshes the ccc
semantic index for local ones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from engine.integrations.github_client import parse_owner_repo
from engine.integrations.gitlab_client import parse_gitlab_path
from engine.models import Codebase
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


def _codebases_dir() -> Path:
    return Path(settings.TETHERDUST_CODEBASES_DIR)


def resolve_local_root(local_root: str) -> Path | None:
    """Resolve a ``local_root`` to a directory under the codebases dir.

    Returns the resolved path only if it stays within the codebases dir and is
    an existing directory; otherwise ``None`` (rejects path traversal).
    """
    if not local_root:
        return None
    base = _codebases_dir().resolve()
    target = (base / local_root).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_dir() else None


def top_level_codebase_folders() -> list[str]:
    """Top-level folder names under sources/codebases/ (for the register dropdown)."""
    base = _codebases_dir()
    if not base.exists() or not base.is_dir():
        return []
    return sorted(
        entry.name for entry in base.iterdir() if entry.is_dir() and not entry.name.startswith(".")
    )


def _enqueue_sync(codebase_id: str) -> None:
    """Dispatch the sync task, falling back to an inline run if Celery is down."""
    from engine.tasks import sync_codebase

    try:
        sync_codebase.delay(codebase_id)
    except Exception:
        sync_codebase(codebase_id)


class CodebaseSerializer(serializers.ModelSerializer[Codebase]):
    access_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    has_token = serializers.SerializerMethodField()

    class Meta(SerializerMeta):
        model = Codebase
        fields = [
            "id",
            "name",
            "description",
            "provider",
            "repo_url",
            "local_root",
            "access_token",
            "has_token",
            "is_active",
            "sync_status",
            "sync_error",
            "last_synced_at",
            "default_branch",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "has_token",
            "sync_status",
            "sync_error",
            "last_synced_at",
            "default_branch",
            "created_at",
            "updated_at",
        ]

    def get_has_token(self, obj: Codebase) -> bool:
        return bool(obj.access_token)

    def validate(self, attrs: Any) -> Any:
        provider = attrs.get("provider")
        if provider is None:
            provider = self.instance.provider if self.instance is not None else "github"

        if provider == "local":
            local_root = attrs.get("local_root")
            if local_root is None and self.instance is not None:
                local_root = self.instance.local_root
            if not local_root:
                raise serializers.ValidationError(
                    {"local_root": "Select a folder under sources/codebases/."}
                )
            if resolve_local_root(local_root) is None:
                raise serializers.ValidationError(
                    {"local_root": "Folder not found under sources/codebases/."}
                )
            return attrs

        repo_url = attrs.get("repo_url")
        if repo_url is None and self.instance is not None:
            repo_url = self.instance.repo_url
        if not repo_url:
            raise serializers.ValidationError(
                {"repo_url": "A repository URL is required for GitHub/GitLab codebases."}
            )

        try:
            if provider == "gitlab":
                parse_gitlab_path(repo_url)
            else:
                parse_owner_repo(repo_url)
        except ValueError as exc:
            message = (
                "Enter a GitLab repository URL like https://gitlab.com/group/project"
                if provider == "gitlab"
                else "Enter a GitHub repository URL like https://github.com/owner/repo"
            )
            raise serializers.ValidationError({"repo_url": message}) from exc
        return attrs

    def create(self, validated_data: Any) -> Codebase:
        token = validated_data.pop("access_token", "")
        instance = Codebase(**validated_data)
        if token:
            instance.access_token = token
        instance.save()
        return instance

    def update(self, instance: Codebase, validated_data: Any) -> Codebase:
        token = validated_data.pop("access_token", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if token:  # only overwrite when a non-empty token is supplied
            instance.access_token = token
        instance.save()
        return instance


class CodebaseViewSet(viewsets.ModelViewSet[Codebase]):
    """Staff CRUD for codebases; saving / `sync` kicks off the tree-caching sync."""

    permission_classes = [IsStaffUser]
    queryset = Codebase.objects.all()
    serializer_class = CodebaseSerializer

    def perform_create(self, serializer: Any) -> None:
        codebase = serializer.save()
        _enqueue_sync(codebase.pk)

    @action(detail=True, methods=["post"])
    def sync(self, request: Request, pk: str | None = None) -> Response:
        codebase = self.get_object()
        codebase.sync_status = Codebase.SYNC_SYNCING
        codebase.sync_error = ""
        codebase.save(update_fields=["sync_status", "sync_error", "updated_at"])
        _enqueue_sync(codebase.pk)
        return Response({"sync_status": codebase.sync_status})

    @action(detail=False, methods=["get"])
    def folders(self, request: Request) -> Response:
        """Top-level folders under sources/codebases/ (for the register dropdown)."""
        registered = set(
            Codebase.objects.filter(provider="local").values_list("local_root", flat=True)
        )
        return Response(
            {
                "folders": [
                    {"name": name, "registered": name in registered}
                    for name in top_level_codebase_folders()
                ]
            }
        )
