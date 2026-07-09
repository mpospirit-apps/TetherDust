"""Tool: search_codebase — search code within a codebase via GitHub or GitLab code search."""

import logging
from typing import Annotated

from pydantic import Field

from ..utils.github_client import GitHubClient, GitHubError, parse_owner_repo
from ..utils.gitlab_client import GitLabClient, GitLabError, parse_gitlab_path
from . import _ccc_client
from ._codebase_local import ccc_project
from ._codebase_shared import get_codebase

logger = logging.getLogger(__name__)


def _format_local_results(codebase: str, query: str, results: list[dict[str, object]]) -> str:
    if not results:
        return f"No matches for '{query}' in codebase '{codebase}'."
    lines = [f"# Semantic code search in {codebase} for: {query}\n"]
    for r in results:
        path = str(r.get("path", ""))
        rng = r.get("lines")
        head = f"- {path}" + (f":{rng}" if rng else "")
        score = r.get("score")
        if isinstance(score, int | float):
            head += f"  (score {score:.2f})"
        lines.append(head)
        snippet = str(r.get("snippet") or "").strip()
        if snippet:
            lines.append(f"```\n{snippet}\n```")
    lines.append("\nUse read_codebase_file to open any of these files.")
    return "\n".join(lines)


_FALLBACK = (
    "Code search is unavailable for this codebase "
    "(GitHub/GitLab code search needs an access token, only indexes the default branch, "
    "and isn't available for every repository). Browse with get_codebase_tree and "
    "read files with read_codebase_file instead."
)


async def search_codebase(
    codebase: Annotated[str, Field(description="Name of the codebase (from list_codebases)")],
    query: Annotated[str, Field(description="Search terms, e.g. a function or symbol name")],
) -> str:
    """Search for code within a codebase by keyword. \
Uses GitHub or GitLab code search for remote codebases (default branch only; may require an \
access token) and ccc semantic search for local codebases. If search is unavailable, fall \
back to get_codebase_tree and read_codebase_file to navigate the repository."""
    cb = get_codebase(codebase)
    if cb is None:
        return (
            f"Codebase '{codebase}' not found or not available for your role. Try list_codebases."
        )
    if not query.strip():
        return "Error: query is required."

    if cb.provider == "local":
        if not _ccc_client.is_configured():
            return (
                "Semantic code search is unavailable (ccc service not configured). "
                "Browse with get_codebase_tree and read files with read_codebase_file instead."
            )
        try:
            results = _ccc_client.search(ccc_project(cb), query, limit=10)
        except _ccc_client.CccError as exc:
            return f"{_FALLBACK}\n\n(Reason: {exc})"
        except Exception:
            logger.exception("Unexpected error searching local codebase %s", codebase)
            return _FALLBACK
        return _format_local_results(codebase, query, results)

    try:
        if cb.provider == "gitlab":
            project = parse_gitlab_path(cb.repo_url)
            gl_client = GitLabClient(token=cb.access_token or None)
            hits = gl_client.search_code(project, query)
        else:
            owner, repo = parse_owner_repo(cb.repo_url)
            gh_client = GitHubClient(token=cb.access_token or None)
            hits = gh_client.search_code(owner, repo, query)
    except (GitHubError, GitLabError) as exc:
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
