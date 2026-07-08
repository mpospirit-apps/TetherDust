"""Glob-based file-tree filtering, shared by every codebase provider client.

Provider clients (``github_client.py``, ``gitlab_client.py``) normalize their
raw API tree responses into ``[{path, type, size}]`` before calling
``filter_tree`` here — this module has no provider-specific knowledge.
"""

from __future__ import annotations

import fnmatch
from typing import Any


def _matches(path: str, pattern: str) -> bool:
    """True if *path* matches *pattern*, tolerating nested dirs and basenames."""
    base = path.rsplit("/", 1)[-1]
    return (
        fnmatch.fnmatch(path, pattern)
        or fnmatch.fnmatch(path, f"*/{pattern}")
        or fnmatch.fnmatch(base, pattern)
    )


def matches_any(path: str, patterns: list[str]) -> bool:
    """True if *path* matches any of *patterns*."""
    return any(_matches(path, p) for p in patterns)


def filter_tree(
    entries: list[dict[str, Any]],
    subpath: str = "",
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten a raw provider tree into ``[{path, type, size}]`` applying scope filters.

    - ``subpath`` keeps only entries under that directory (paths are returned
      relative to it).
    - ``include_globs`` (if non-empty) keeps only matching files.
    - ``exclude_globs`` drops matching files.
    Directory (``tree``) entries are dropped from the output — only blobs/files.
    """
    include_globs = include_globs or []
    exclude_globs = exclude_globs or []
    sub = subpath.strip("/")
    prefix = f"{sub}/" if sub else ""

    result: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("type") != "blob":
            continue
        full = entry.get("path", "")
        if prefix and not full.startswith(prefix):
            continue
        rel = full[len(prefix) :] if prefix else full
        if not rel:
            continue
        if exclude_globs and matches_any(rel, exclude_globs):
            continue
        if include_globs and not matches_any(rel, include_globs):
            continue
        result.append({"path": rel, "type": "file", "size": entry.get("size")})
    return result
