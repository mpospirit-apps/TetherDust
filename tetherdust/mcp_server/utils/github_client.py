"""Minimal GitHub REST API client for the MCP codebase tools.

A standalone copy of the Django-side client (the ``mcp`` container cannot import
``core``). Used for live tree/file/search reads against GitHub.
"""

from __future__ import annotations

import base64
import fnmatch
from typing import Any, cast

import httpx

GITHUB_API = "https://api.github.com"
MAX_FILE_BYTES = 256 * 1024


class GitHubError(Exception):
    """Base error for GitHub API problems (carries a user-facing message)."""


class GitHubAuthError(GitHubError):
    """Authentication failed or the token lacks access to the repository."""


class GitHubNotFoundError(GitHubError):
    """Repository, ref, or path not found."""


class GitHubRateLimitError(GitHubError):
    """GitHub API rate limit exceeded."""


def _matches(path: str, pattern: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return (
        fnmatch.fnmatch(path, pattern)
        or fnmatch.fnmatch(path, f"*/{pattern}")
        or fnmatch.fnmatch(base, pattern)
    )


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(_matches(path, p) for p in patterns)


def parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Parse a GitHub repo URL into (owner, repo). Raises ValueError if invalid."""
    url = (repo_url or "").strip()
    if not url:
        raise ValueError("Repository URL is required.")
    if url.startswith("git@"):
        _, _, path = url.partition(":")
    else:
        path = url.split("://", 1)[-1]
        path = path.split("/", 1)[1] if "/" in path else ""
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {repo_url!r}")
    return parts[0], parts[1]


class GitHubClient:
    """Thin wrapper over the GitHub REST API with typed errors."""

    def __init__(self, token: str | None = None, timeout: float = 20.0):
        self._token = token or None
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            resp = httpx.get(url, headers=self._headers(), params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise GitHubError(f"Could not reach GitHub: {exc}") from exc

        if resp.status_code in (401, 403):
            if resp.headers.get("X-RateLimit-Remaining") == "0":
                raise GitHubRateLimitError(
                    "GitHub API rate limit exceeded. Add an access token or try again later."
                )
            raise GitHubAuthError(
                "GitHub denied access (private repos require a token with read access)."
            )
        if resp.status_code == 404:
            raise GitHubNotFoundError(
                "Not found on GitHub (check the repository, branch, or path)."
            )
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._get(f"{GITHUB_API}/repos/{owner}/{repo}").json())

    def get_tree(self, owner: str, repo: str, ref: str) -> list[dict[str, Any]]:
        resp = self._get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        return resp.json().get("tree", []) or []

    def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict[str, Any]:
        resp = self._get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        data = resp.json()
        if isinstance(data, list):
            raise GitHubError(f"'{path}' is a directory, not a file.")
        size = data.get("size", 0) or 0
        if size > MAX_FILE_BYTES:
            raise GitHubError(
                f"File '{path}' is {size} bytes, larger than the {MAX_FILE_BYTES}-byte limit."
            )
        if data.get("encoding") != "base64" or not data.get("content"):
            raise GitHubError(f"File '{path}' could not be decoded (likely binary or empty).")
        raw = base64.b64decode(data["content"])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitHubError(f"File '{path}' is not UTF-8 text (likely binary).") from exc
        return {"path": path, "size": size, "text": text}

    def search_code(
        self, owner: str, repo: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        resp = self._get(
            f"{GITHUB_API}/search/code",
            params={"q": f"{query} repo:{owner}/{repo}", "per_page": str(limit)},
        )
        items = resp.json().get("items", []) or []
        return [{"path": it.get("path", "")} for it in items]
