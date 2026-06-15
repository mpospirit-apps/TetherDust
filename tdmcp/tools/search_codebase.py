"""Tool: search_codebase — search code within a codebase via GitHub code search."""

import logging
from typing import Annotated

from pydantic import Field

from ..utils.github_client import GitHubClient, GitHubError, parse_owner_repo
from ._codebase_shared import get_codebase

logger = logging.getLogger(__name__)

_FALLBACK = (
    "Code search is unavailable for this codebase "
    "(GitHub code search needs an access token, only indexes the default branch, "
    "and isn't available for every repository). Browse with get_codebase_tree and "
    "read files with read_codebase_file instead."
)


async def search_codebase(
    codebase: Annotated[str, Field(description="Name of the codebase (from list_codebases)")],
    query: Annotated[str, Field(description="Search terms, e.g. a function or symbol name")],
) -> str:
    """Search for code within a codebase by keyword. \
Uses GitHub code search (default branch only; requires the codebase to have an \
access token). If search is unavailable, fall back to get_codebase_tree and \
read_codebase_file to navigate the repository."""
    cb = get_codebase(codebase)
    if cb is None:
        return (
            f"Codebase '{codebase}' not found or not available for your role. Try list_codebases."
        )
    if not query.strip():
        return "Error: query is required."

    try:
        owner, repo = parse_owner_repo(cb.repo_url)
        client = GitHubClient(token=cb.access_token or None)
        hits = client.search_code(owner, repo, query)
    except GitHubError as exc:
        return f"{_FALLBACK}\n\n(Reason: {exc})"
    except Exception:
        logger.exception("Unexpected error searching codebase %s", codebase)
        return _FALLBACK

    # Honor the configured subpath when filtering results.
    sub = cb.subpath.strip("/")
    paths = []
    for h in hits:
        p = h.get("path", "")
        if sub and not (p == sub or p.startswith(sub + "/")):
            continue
        paths.append(p[len(sub) + 1 :] if sub and p.startswith(sub + "/") else p)

    if not paths:
        return f"No matches for '{query}' in codebase '{codebase}'."

    lines = [f"# Code search results in {codebase} for: {query}\n"]
    for p in paths:
        lines.append(f"- {p}")
    lines.append("\nUse read_codebase_file to open any of these files.")
    return "\n".join(lines)
