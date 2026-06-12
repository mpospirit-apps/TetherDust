"""Tool: read_codebase_file — read a single file from a codebase via GitHub."""

import logging
from typing import Annotated

from pydantic import Field

from ..utils.github_client import GitHubClient, GitHubError, parse_owner_repo
from ._codebase_shared import get_codebase

logger = logging.getLogger(__name__)


async def read_codebase_file(
    codebase: Annotated[str, Field(description="Name of the codebase (from list_codebases)")],
    path: Annotated[str, Field(description="File path within the repository, e.g. 'src/app.py'")],
) -> str:
    """Read the full contents of a single file from a codebase. \
Fetches the file live from GitHub on the codebase's branch. Use get_codebase_tree \
first to find the exact path. Large files and binaries are refused."""
    cb = get_codebase(codebase)
    if cb is None:
        return (
            f"Codebase '{codebase}' not found or not available for your role. Try list_codebases."
        )

    rel = path.strip("/")
    # Honor the codebase subpath so paths are relative to the configured root.
    full_path = f"{cb.subpath.strip('/')}/{rel}" if cb.subpath else rel

    try:
        owner, repo = parse_owner_repo(cb.repo_url)
        client = GitHubClient(token=cb.access_token or None)
        result = client.get_file(owner, repo, full_path, cb.ref)
    except GitHubError as exc:
        return f"Could not read '{path}' from '{codebase}': {exc}"
    except ValueError as exc:
        return f"Invalid codebase configuration for '{codebase}': {exc}"
    except Exception:
        logger.exception("Unexpected error reading %s from codebase %s", path, codebase)
        return f"Unexpected error reading '{path}' from '{codebase}'."

    return f"# {codebase}: {path}\n\n```\n{result['text']}\n```"
