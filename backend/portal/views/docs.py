"""Documentation views and the wiki-link markdown extension."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import escape as html_escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload

import markdown
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from markdown import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

# Extension → highlight.js language name for code file rendering in docs
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

WIKILINK_RE = r"\[\[([^\]]+)\]\]"


class WikiLinkInlineProcessor(InlineProcessor):
    """Converts [[Source/path.md]] or [[Source/path.md|Display]] to links."""

    def __init__(
        self,
        pattern: str,
        md: Any,
        user: AbstractUser | None = None,
        current_source: str | None = None,
    ) -> None:
        super().__init__(pattern, md)
        self.user = user
        self.current_source = current_source
        self._source_cache: dict[str, int | None] = {}
        self._allowed_sources: set[str] | None = None
        self._allowed_sources_loaded: bool = False

    def _get_allowed_sources(self) -> set[str] | None:
        """Lazy-load allowed doc sources for current user."""
        if self._allowed_sources_loaded:
            return self._allowed_sources

        if not self.user or not self.user.is_authenticated:
            self._allowed_sources = set()
            self._allowed_sources_loaded = True
            return self._allowed_sources
        if self.user.is_staff:
            self._allowed_sources = None  # staff sees all
            self._allowed_sources_loaded = True
            return None
        profile = getattr(self.user, "profile", None)
        if not profile:
            self._allowed_sources = set()
            self._allowed_sources_loaded = True
            return self._allowed_sources
        self._allowed_sources = profile.get_allowed_doc_sources()
        self._allowed_sources_loaded = True
        return self._allowed_sources

    def _resolve_source(self, folder_name: str) -> int | None:
        """Look up DocumentationSource id by folder_name, with caching."""
        if folder_name in self._source_cache:
            return self._source_cache[folder_name]
        from core.models import DocumentationSource

        source = DocumentationSource.objects.filter(folder_name=folder_name, is_active=True).first()
        source_id = source.pk if source else None
        self._source_cache[folder_name] = source_id
        return source_id

    @overload
    def handleMatch(self, m: re.Match[str]) -> str | ET.Element | None: ...  # noqa: N802

    @overload
    def handleMatch(
        self, m: re.Match[str], data: str
    ) -> tuple[ET.Element | str | None, int | None, int | None]: ...  # noqa: N802

    def handleMatch(  # noqa: N802
        self, m: re.Match[str], data: str = ""
    ) -> tuple[ET.Element | str | None, int | None, int | None] | str | ET.Element | None:

        raw = m.group(1)
        if "|" in raw:
            link_path, display = raw.split("|", 1)
        else:
            link_path = raw
            display = link_path.rsplit("/", 1)[-1]
            if display.endswith(".md"):
                display = display[:-3]

        link_path = link_path.strip()
        display = display.strip()

        if "/" in link_path:
            folder_name = link_path.split("/", 1)[0]
            file_path = link_path.split("/", 1)[1]
        elif link_path.endswith(".md") and self.current_source:
            # Bare same-source link, e.g. [[Page.md|Display]] — resolve it
            # against the source the current page lives in.
            folder_name = self.current_source
            file_path = link_path
        else:
            folder_name = link_path
            file_path = ""

        source_id = self._resolve_source(folder_name)
        allowed = self._get_allowed_sources()
        has_access = source_id is not None and (allowed is None or folder_name in allowed)

        if has_access and file_path:
            el = ET.Element("a")
            el.set("class", "wikilink")
            el.set("data-url", f"/docs/{source_id}/{file_path}")
            el.set("onclick", "loadWikiLink(this); return false;")
            el.set("href", "#")
            el.text = display
        else:
            el = ET.Element("span")
            el.set("class", "wikilink-noaccess")
            el.set(
                "title",
                "This page doesn't exist or you don't have permission",
            )
            el.text = display

        return el, m.start(0), m.end(0)


class WikiLinkExtension(Extension):
    def __init__(
        self,
        user: AbstractUser | None = None,
        current_source: str | None = None,
        **kwargs: object,
    ) -> None:
        self.user = user
        self.current_source = current_source
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:  # noqa: N802
        md.inlinePatterns.register(
            WikiLinkInlineProcessor(
                WIKILINK_RE, md, user=self.user, current_source=self.current_source
            ),
            "wikilink",
            175,
        )


def _build_file_tree(base_path: Path, patterns: list[str]) -> list[dict[str, object]]:
    """Build a nested file tree from a documentation source path.

    Returns a list of dicts: {"name", "path" (relative), "type" ("file"|"dir"), "children"}.
    """
    if not base_path.is_dir():
        return []

    matched_files: set[Path] = set()
    for pattern in patterns or ["*.md"]:
        matched_files.update(base_path.rglob(pattern))

    dirs_with_files: set[Path] = set()
    for f in matched_files:
        parent = f.parent
        while parent != base_path:
            dirs_with_files.add(parent)
            parent = parent.parent

    def _scan(directory: Path) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
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
                is_md = child.suffix.lower() == ".md"
                entries.append(
                    {
                        "name": child.stem if is_md else child.name,
                        "path": str(rel),
                        "type": "file",
                        "is_code": not is_md,
                    }
                )
        return entries

    return _scan(base_path)


@login_required
def docs_view(request: HttpRequest) -> HttpResponse:
    """Documentation viewer — sidebar tree + rendered markdown."""
    from core.models import DocumentationSource

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        sources = DocumentationSource.objects.filter(is_active=True).order_by("folder_name")
    else:
        profile = getattr(user, "profile", None)
        if not profile or not profile.can_view_docs:
            return render(request, "portal/docs.html", {"sources": [], "has_access": False})
        allowed_names = profile.get_allowed_doc_sources()
        if allowed_names is None:
            sources = DocumentationSource.objects.filter(is_active=True).order_by("folder_name")
        else:
            sources = DocumentationSource.objects.filter(
                is_active=True, folder_name__in=allowed_names
            ).order_by("folder_name")
    source_trees = []
    for src in sources:
        base = Path(src.resolved_path)
        tree = _build_file_tree(base, src.file_patterns or ["*.md"])
        source_trees.append(
            {
                "id": src.pk,
                "name": src.folder_name,
                "doc_type": src.doc_type,
                "tree": tree,
            }
        )

    auto_open = None
    open_path = request.GET.get("open", "").strip()
    if open_path:
        slash_idx = open_path.find("/")
        if slash_idx > 0:
            source_name = open_path[:slash_idx]
            file_path = open_path[slash_idx + 1 :]
            try:
                src = sources.get(folder_name=source_name)
                auto_open = {
                    "source_id": src.pk,
                    "file_path": file_path,
                    "doc_name": Path(file_path).stem,
                }
            except Exception:
                pass

    return render(
        request,
        "portal/docs.html",
        {
            "sources": source_trees,
            "has_access": True,
            "auto_open": auto_open,
        },
    )


@login_required
def docs_content_view(request: HttpRequest, source_id: int, file_path: str) -> HttpResponse:
    """HTMX endpoint — returns server-rendered markdown HTML for a doc file."""
    from core.models import DocumentationSource

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        allowed_ids = set(
            DocumentationSource.objects.filter(is_active=True).values_list("id", flat=True)
        )
    else:
        profile = getattr(user, "profile", None)
        if not profile:
            return HttpResponse("<p>Access denied.</p>", status=403)
        allowed_names = profile.get_allowed_doc_sources()
        if allowed_names is None:
            allowed_ids = set(
                DocumentationSource.objects.filter(is_active=True).values_list("id", flat=True)
            )
        else:
            allowed_ids = set(
                DocumentationSource.objects.filter(
                    is_active=True, folder_name__in=allowed_names
                ).values_list("id", flat=True)
            )
    if source_id not in allowed_ids:
        return HttpResponse("<p>Access denied.</p>", status=403)

    source = DocumentationSource.objects.get(id=source_id)
    base = Path(source.resolved_path)
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)

    target = (base / file_path).resolve()
    if not str(target).startswith(str(docs_dir.resolve())):
        return HttpResponse("<p>Invalid path.</p>", status=400)
    if not target.is_file():
        return HttpResponse("<p>File not found.</p>", status=404)

    raw = target.read_text(encoding="utf-8")

    if target.suffix.lower() == ".md":
        wikilink_ext = WikiLinkExtension(
            user=cast("AbstractUser", request.user), current_source=source.folder_name
        )
        md = markdown.Markdown(
            extensions=["fenced_code", "tables", "toc", "codehilite", wikilink_ext]
        )
        html = md.convert(raw)
    else:
        lang = _EXT_TO_LANG.get(target.suffix.lower(), "")
        lang_cls = f' class="language-{lang}"' if lang else ""
        html = f"<pre><code{lang_cls}>{html_escape(raw)}</code></pre>"

    return HttpResponse(html)
