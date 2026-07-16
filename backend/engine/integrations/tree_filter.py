"""File-tree flattening, shared by every codebase provider client.

Provider clients (``github_client.py``, ``gitlab_client.py``) normalize their
raw API tree responses into ``[{path, type, size}]`` before calling
``filter_tree`` here — this module has no provider-specific knowledge.
"""

from __future__ import annotations

from typing import Any


def filter_tree(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten a raw provider tree into ``[{path, type, size}]``.

    Directory (``tree``) entries are dropped from the output — only
    blobs/files.
    """
    return [
        {"path": entry.get("path", ""), "type": "file", "size": entry.get("size")}
        for entry in entries
        if entry.get("type") == "blob"
    ]
