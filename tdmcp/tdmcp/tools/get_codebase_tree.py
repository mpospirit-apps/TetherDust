"""Tool: get_codebase_tree — list files in a codebase from its cached tree."""

from typing import Annotated

from pydantic import Field

from ._codebase_local import walk_tree
from ._codebase_shared import get_codebase

_MAX_ENTRIES = 800


async def get_codebase_tree(
    codebase: Annotated[str, Field(description="Name of the codebase (from list_codebases)")],
    path: Annotated[
        str, Field(description="Optional sub-directory to scope to, e.g. 'src/api'")
    ] = "",
) -> str:
    """List the files in a codebase, optionally under a sub-directory. \
For remote codebases, returns paths from the cached tree (refreshed on sync); for local \
codebases, walks the filesystem live. Use this to discover where code lives before \
reading specific files with read_codebase_file."""
    cb = get_codebase(codebase)
    if cb is None:
        return (
            f"Codebase '{codebase}' not found or not available for your role. Try list_codebases."
        )

    if cb.provider == "local":
        entries = walk_tree(cb, path)
        if not entries:
            scope = f" under '{path}'" if path else ""
            return f"No files found{scope} in codebase '{codebase}'."
    else:
        if not cb.cached_tree:
            return (
                f"Codebase '{codebase}' has no cached file tree yet. "
                "Ask an administrator to Sync it from the Codebases page."
            )

        prefix = path.strip("/")
        if prefix:
            prefix_slash = prefix + "/"
            entries = [
                e
                for e in cb.cached_tree
                if e.get("path", "") == prefix or e.get("path", "").startswith(prefix_slash)
            ]
        else:
            entries = list(cb.cached_tree)

        if not entries:
            return f"No files found under '{path}' in codebase '{codebase}'."

    total = len(entries)
    entries = sorted(entries, key=lambda e: str(e.get("path", "")))[:_MAX_ENTRIES]

    lines = [f"# Files in {codebase}" + (f" under {path}" if path else "")]
    lines.append("")
    for e in entries:
        size = e.get("size")
        size_str = f"  ({size} bytes)" if size else ""
        lines.append(f"- {e.get('path', '')}{size_str}")
    if total > len(entries):
        lines.append(f"\n…and {total - len(entries)} more. Narrow the search with a `path`.")
    return "\n".join(lines)
