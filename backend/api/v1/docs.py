"""Public documentation API — role-scoped source tree + raw Markdown/code.

Replaces the legacy ``workspace/views/docs.py``. Content is returned as **raw**
Markdown (or raw source for code files) plus metadata; the React SPA renders it
and resolves ``[[Source/path|Display]]`` wiki-links to ``/docs/<source>/<path>``
routes (the WikiLink markdown extension moves client-side).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings
from engine.models import DocumentationSource
from engine.services import DocSourceService, PermissionService, get
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewDocs

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.contrib.auth.models import AbstractUser
    from django.db.models import QuerySet

# Extension → highlight.js language name for code-file rendering in the SPA.
_EXT_TO_LANG: dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".toml": "toml",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".php": "php",
    ".r": "r",
    ".lua": "lua",
    ".dockerfile": "dockerfile",
    ".tf": "hcl",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".vue": "xml",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".cshtml": "cshtml",
    ".csproj": "xml",
    ".sln": "plaintext",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "nginx",
    ".env": "bash",
    ".ps1": "powershell",
}


def _build_file_tree(base_path: Path) -> list[dict[str, Any]]:
    """Build a nested file tree of Markdown files from a documentation source path.

    Returns a list of dicts: {"name", "path" (relative), "type" ("file"|"dir"),
    "children"}.
    """
    if not base_path.is_dir():
        return []

    matched_files = set(base_path.rglob("*.md"))

    dirs_with_files: set[Path] = set()
    for f in matched_files:
        parent = f.parent
        while parent != base_path:
            dirs_with_files.add(parent)
            parent = parent.parent

    def _scan(directory: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for child in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name.startswith("."):
                continue
            rel = child.relative_to(base_path)
            if child.is_dir() and child in dirs_with_files:
                entries.append(
                    {
                        "name": child.name,
                        "path": str(rel),
                        "type": "dir",
                        "children": _scan(child),
                    }
                )
            elif child.is_file() and child in matched_files:
                entries.append(
                    {
                        "name": child.stem,
                        "path": str(rel),
                        "type": "file",
                    }
                )
        return entries

    return _scan(base_path)


def _visible_sources(user: AbstractUser) -> QuerySet[DocumentationSource]:
    """Active doc sources the user may see (staff → all; else role-allowed)."""
    base = DocumentationSource.objects.filter(is_active=True).order_by("folder_name")
    if user.is_staff:
        return base
    profile = getattr(user, "profile", None)
    if not profile:
        return base.none()
    allowed_names: Iterable[str] | None = get(PermissionService).get_allowed_doc_sources(profile)
    if allowed_names is None:
        return base
    return base.filter(folder_name__in=allowed_names)


class DocsSourcesView(APIView):
    """Role-scoped documentation sources, each with its nested file tree."""

    permission_classes = [CanViewDocs]

    def get(self, request: Request) -> Response:
        # No filesystem sync here (matches the legacy workspace view): the admin
        # doc-source list reconciles disk↔DB, and docgen syncs after writing.
        user = cast("AbstractUser", request.user)
        sources = _visible_sources(user)
        result: list[dict[str, Any]] = []
        for src in sources:
            base = Path(get(DocSourceService).resolved_path(src))
            result.append(
                {
                    "id": src.pk,
                    "name": src.folder_name,
                    "doc_type": src.doc_type,
                    "tree": _build_file_tree(base),
                }
            )
        return Response({"sources": result})


class DocsContentView(APIView):
    """Raw Markdown/code + metadata for a single file in a (visible) source."""

    permission_classes = [CanViewDocs]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        source_name = (request.query_params.get("source") or "").strip()
        file_path = (request.query_params.get("path") or "").strip()
        if not source_name or not file_path:
            return Response(
                {"detail": "Both 'source' and 'path' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        source = _visible_sources(user).filter(folder_name=source_name).first()
        if source is None:
            return Response({"detail": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        base = Path(get(DocSourceService).resolved_path(source))
        docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
        target = (base / file_path).resolve()
        if not str(target).startswith(str(docs_dir.resolve())):
            return Response({"detail": "Invalid path."}, status=status.HTTP_400_BAD_REQUEST)
        if not target.is_file():
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)

        raw = target.read_text(encoding="utf-8", errors="replace")
        is_markdown = target.suffix.lower() == ".md"
        return Response(
            {
                "source": source.folder_name,
                "path": file_path,
                "title": target.stem if is_markdown else target.name,
                "is_markdown": is_markdown,
                "language": "" if is_markdown else _EXT_TO_LANG.get(target.suffix.lower(), ""),
                "content": raw,
            }
        )
