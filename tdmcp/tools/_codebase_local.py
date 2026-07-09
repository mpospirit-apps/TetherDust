"""Local-codebase helpers: live filesystem reads under ``sources/codebases/``.

The ``mcp`` container mounts ``sources/codebases`` read-only. Local codebases are
read live from disk (no clone, no cached tree); semantic search is delegated to
the ccc service over HTTP by ``search_codebase``. Every path operation is
contained within the codebase root to reject traversal via ``..``/symlinks.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..utils.github_client import matches_any
from ._codebase_shared import CodebaseConfig

# Applied when the codebase configures no excludes, so the agent isn't flooded
# with build output/binaries (mirrors engine.models.Codebase.DEFAULT_EXCLUDE_GLOBS).
_DEFAULT_EXCLUDE_GLOBS = [
    "node_modules/*",
    "dist/*",
    "build/*",
    "vendor/*",
    "*.lock",
    "*.min.js",
    "*.map",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.ico",
    "*.webp",
    "*.pdf",
    "*.zip",
    "*.gz",
    "*.tar",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
]

# Files above this are refused by read_codebase_file (matches the remote cap).
MAX_FILE_BYTES = 256 * 1024


def codebases_dir() -> Path:
    return Path(os.environ.get("TETHERDUST_CODEBASES_DIR", "/app/sources/codebases"))


def ccc_project(cb: CodebaseConfig) -> str:
    """The ccc project path (relative to the ccc ``/app`` mount) for a local codebase.

    Kept in sync with the backend's ``engine.tasks`` indexing call so search hits
    resolve against the same root as ``read_codebase_file`` / ``get_codebase_tree``.
    """
    project = "sources/codebases/" + cb.local_root.strip("/")
    if cb.subpath:
        project += "/" + cb.subpath.strip("/")
    return project


def _contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def codebase_root(cb: CodebaseConfig) -> Path | None:
    """Resolve the codebase's on-disk root (dir / local_root / subpath), or None."""
    if not cb.local_root:
        return None
    base = codebases_dir().resolve()
    root = (base / cb.local_root).resolve()
    if not _contained(root, base):
        return None
    if cb.subpath:
        root = (root / cb.subpath.strip("/")).resolve()
        if not _contained(root, base):
            return None
    return root if root.is_dir() else None


def resolve_file(cb: CodebaseConfig, rel: str) -> Path | None:
    """Resolve *rel* within the codebase root, rejecting traversal. None if absent."""
    root = codebase_root(cb)
    if root is None:
        return None
    target = (root / rel.strip("/")).resolve()
    if not _contained(target, root):
        return None
    return target if target.is_file() else None


def _excluded(rel: str, cb: CodebaseConfig) -> bool:
    if any(part.startswith(".") for part in Path(rel).parts):
        return True  # hidden dirs/files incl. ccc's .cocoindex_code index
    return matches_any(rel, cb.exclude_globs or _DEFAULT_EXCLUDE_GLOBS)


def walk_tree(cb: CodebaseConfig, subdir: str = "") -> list[dict[str, object]]:
    """List files under the codebase root (optionally under *subdir*), filtered.

    Returns ``[{"path", "size"}]`` with paths relative to the codebase root.
    """
    root = codebase_root(cb)
    if root is None:
        return []
    start = (root / subdir.strip("/")).resolve() if subdir else root
    if not _contained(start, root) or not start.is_dir():
        return []

    entries: list[dict[str, object]] = []
    for path in start.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if _excluded(rel, cb):
            continue
        if cb.include_globs and not matches_any(rel, cb.include_globs):
            continue
        entries.append({"path": rel, "size": path.stat().st_size})
    return entries
