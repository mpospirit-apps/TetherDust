"""Minimal GitLab REST API (v4) client for the MCP codebase tools.

A standalone copy of the Django-side client (the ``mcp`` container cannot
import ``engine``), trimmed to what the MCP tools need for live reads:
``get_file`` and ``search_code``. Tree building/pagination lives only on the
Django side (``sync_codebase``) — the MCP tools read the already-filtered
``cached_tree`` column instead. gitlab.com only, no self-managed instances.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import httpx

GITLAB_API = "https://gitlab.com/api/v4"
MAX_FILE_BYTES = 256 * 1024


def parse_gitlab_path(repo_url: str) -> str:
    """Parse a GitLab project URL into its full namespace path.

    Unlike GitHub's flat owner/repo, GitLab projects can live under nested
    subgroups, so this returns the whole path rather than a 2-tuple. Strips
    a trailing ``/-/...`` route segment before splitting.
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
                "GitLab denied access (private projects require a token with read access)."
            )
        if resp.status_code == 404:
            raise GitLabNotFoundError(
                "Not found on GitLab (check the repository, branch, or path)."
            )
        if resp.status_code >= 400:
            raise GitLabError(f"GitLab API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_file(self, path: str, file_path: str, ref: str) -> dict[str, Any]:
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
        resp = self._get(
            f"{GITLAB_API}/projects/{_encode(path)}/search",
            params={"scope": "blobs", "search": query, "per_page": str(limit)},
        )
        items = resp.json() or []
        return [{"path": it.get("path", "")} for it in items]
