"""Tool: read_codebase_file — read a single file from a codebase via GitHub or GitLab."""

import logging
from typing import Annotated

from pydantic import Field

from ..utils.github_client import GitHubClient, GitHubError, parse_owner_repo
from ..utils.gitlab_client import GitLabClient, GitLabError, parse_gitlab_path
from ._codebase_local import MAX_FILE_BYTES, resolve_file
from ._codebase_shared import get_codebase

logger = logging.getLogger(__name__)


async def read_codebase_file(
    codebase: Annotated[str, Field(description="Name of the codebase (from list_codebases)")],
    path: Annotated[str, Field(description="File path within the repository, e.g. 'src/app.py'")],
) -> str:
    """Read the full contents of a single file from a codebase. \
Fetches the file live from GitHub or GitLab (or from disk for local codebases) on the \
codebase's branch. Use get_codebase_tree first to find the exact path. Large files and \
binaries are refused."""
    cb = get_codebase(codebase)
    if cb is None:
        return (
            f"Codebase '{codebase}' not found or not available for your role. Try list_codebases."
        )

    if cb.provider == "local":
        target = resolve_file(cb, path)
        if target is None:
            return f"Could not read '{path}' from '{codebase}': file not found."
        try:
            size = target.stat().st_size
            if size > MAX_FILE_BYTES:
                return f"'{path}' is too large ({size} bytes; limit {MAX_FILE_BYTES}) to read."
            data = target.read_bytes()
        except OSError as exc:
            return f"Could not read '{path}' from '{codebase}': {exc}"
        if b"\x00" in data:
            return f"'{path}' appears to be a binary file and can't be displayed."
        return f"# {codebase}: {path}\n\n```\n{data.decode('utf-8', errors='replace')}\n```"

    rel = path.strip("/")

    try:
        if cb.provider == "gitlab":
            project = parse_gitlab_path(cb.repo_url)
            gl_client = GitLabClient(token=cb.access_token or None)
            result = gl_client.get_file(project, rel, cb.ref)
        else:
            owner, repo = parse_owner_repo(cb.repo_url)
            gh_client = GitHubClient(token=cb.access_token or None)
            result = gh_client.get_file(owner, repo, rel, cb.ref)
    except (GitHubError, GitLabError) as exc:
        return f"Could not read '{path}' from '{codebase}': {exc}"
    except ValueError as exc:
        return f"Invalid codebase configuration for '{codebase}': {exc}"
    except Exception:
        logger.exception("Unexpected error reading %s from codebase %s", path, codebase)
        return f"Unexpected error reading '{path}' from '{codebase}'."

    return f"# {codebase}: {path}\n\n```\n{result['text']}\n```"
