"""Minimal GitLab REST API (v4) client for codebase sources.

On-demand reader: no clone, gitlab.com only (self-managed instances are out of
scope — matches the GitHub integration, which is also public-GitHub-only).
The Django side uses this to validate access and cache the repository file
tree on sync; the MCP server keeps its own trimmed copy (it cannot import
Django) for live file/search reads.
"""

from __future__ import annotations

import base64
from typing import Any, cast
from urllib.parse import quote

import httpx

GITLAB_API = "https://gitlab.com/api/v4"
# Mirrors GitHub's contents-API cap; GitLab's file-metadata endpoint also
# returns content inline as base64.
MAX_FILE_BYTES = 256 * 1024
# Sanity bound on tree pagination (100/page from GitLab's max per_page).
MAX_TREE_PAGES = 20


def parse_gitlab_path(repo_url: str) -> str:
    """Parse a GitLab project URL into its full namespace path.

    Unlike GitHub's flat ``owner/repo``, GitLab projects can live under
    arbitrarily nested subgroups (``group/subgroup/project``), so this
    returns the whole path rather than a 2-tuple. Accepts the common forms —
    ``https://gitlab.com/group/project``, ``.../group/subgroup/project``,
    ``.../project.git``, ``git@gitlab.com:group/project.git`` — and strips a
    trailing ``/-/...`` route segment (GitLab's separator for UI routes like
    ``/-/tree/main`` or ``/-/blob/main/file.py``) before splitting. Raises
    ``ValueError`` for anything that doesn't resolve to at least a
    namespace/project pair.
    """
    url = (repo_url or "").strip()
    if not url:
        raise ValueError("Repository URL is required.")

    if url.startswith("git@"):
        _, _, path = url.partition(":")
    else:
        path = url.split("://", 1)[-1]
        path = path.split("/", 1)[1] if "/" in path else ""

    path = path.strip("/")
    path = path.split("/-/", 1)[0]
    if path.endswith(".git"):
        path = path[: -len(".git")]

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse a GitLab project path from URL: {repo_url!r}")
    return "/".join(parts)


class GitLabError(Exception):
    """Base error for GitLab API problems (carries a user-facing message)."""


class GitLabAuthError(GitLabError):
    """Authentication failed or the token lacks access to the project."""


class GitLabNotFoundError(GitLabError):
    """Project, ref, or path not found."""


class GitLabRateLimitError(GitLabError):
    """GitLab API rate limit exceeded."""


def _encode(path: str) -> str:
    """URL-encode a project path or file path for use as a GitLab :id/:file_path."""
    return quote(path, safe="")


class GitLabClient:
    """Thin wrapper over the GitLab REST API (v4) with typed errors."""

    def __init__(self, token: str | None = None, timeout: float = 20.0):
        self._token = token or None
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["PRIVATE-TOKEN"] = self._token
        return headers

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            resp = httpx.get(url, headers=self._headers(), params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise GitLabError(f"Could not reach GitLab: {exc}") from exc

        if resp.status_code == 429:
            raise GitLabRateLimitError(
                "GitLab API rate limit exceeded. Add an access token or try again later."
            )
        if resp.status_code in (401, 403):
            raise GitLabAuthError(
                "GitLab denied access. Check the repository URL and access token "
                "(private projects require a token with read_repository scope)."
            )
        if resp.status_code == 404:
            raise GitLabNotFoundError(
                "Not found on GitLab (check the repository URL, branch, or path)."
            )
        if resp.status_code >= 400:
            raise GitLabError(f"GitLab API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_project(self, path: str) -> dict[str, Any]:
        """Project metadata (includes ``default_branch``)."""
        return cast(dict[str, Any], self._get(f"{GITLAB_API}/projects/{_encode(path)}").json())

    def get_tree(self, path: str, ref: str) -> list[dict[str, Any]]:
        """Full recursive project tree for *ref* — raw entries ``[{path, type, size}]``.

        GitLab paginates the tree endpoint (max 100/page), unlike GitHub's
        single-call recursive tree, so this follows ``X-Next-Page`` until
        exhausted or ``MAX_TREE_PAGES`` is hit. GitLab's tree API has no file
        size, so ``size`` is always ``None`` here.
        """
        pid = _encode(path)
        entries: list[dict[str, Any]] = []
        page = 1
        while page <= MAX_TREE_PAGES:
            resp = self._get(
                f"{GITLAB_API}/projects/{pid}/repository/tree",
                params={
                    "recursive": "true",
                    "per_page": "100",
                    "page": str(page),
                    "ref": ref,
                },
            )
            batch = resp.json()
            if not batch:
                break
            entries.extend(batch)
            if not resp.headers.get("x-next-page"):
                break
            page += 1

        return [
            {
                "path": e.get("path", ""),
                "type": "blob" if e.get("type") == "blob" else "tree",
                "size": None,
            }
            for e in entries
        ]

    def get_file(self, path: str, file_path: str, ref: str) -> dict[str, Any]:
        """Fetch a single file. Returns ``{path, size, text}``.

        Raises GitLabError for directories, binaries, or oversized files.
        """
        resp = self._get(
            f"{GITLAB_API}/projects/{_encode(path)}/repository/files/{_encode(file_path)}",
            params={"ref": ref},
        )
        data = resp.json()
        size = data.get("size", 0) or 0
        if size > MAX_FILE_BYTES:
            raise GitLabError(
                f"File '{file_path}' is {size} bytes, larger than the {MAX_FILE_BYTES}-byte limit."
            )
        if data.get("encoding") != "base64" or not data.get("content"):
            raise GitLabError(f"File '{file_path}' could not be decoded (likely binary or empty).")
        raw = base64.b64decode(data["content"])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitLabError(f"File '{file_path}' is not UTF-8 text (likely binary).") from exc
        return {"path": file_path, "size": size, "text": text}

    def search_code(self, path: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search code within a project (default branch only). Returns path hits.

        Uses GitLab's project-scoped ``scope=blobs`` search, which works
        without Elasticsearch (unlike group/global blob search) but is
        limited to the default branch — the same limitation class as
        GitHub's code search.
        """
        resp = self._get(
            f"{GITLAB_API}/projects/{_encode(path)}/search",
            params={"scope": "blobs", "search": query, "per_page": str(limit)},
        )
        items = resp.json() or []
        return [{"path": it.get("path", "")} for it in items]
