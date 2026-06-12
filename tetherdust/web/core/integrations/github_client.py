"""Minimal GitHub REST API client for codebase sources.

On-demand reader: no clone. The Django side uses this to validate access and
cache the repository file tree on sync; the MCP server keeps its own copy (it
cannot import Django) for live tree/file/search reads.
"""

from __future__ import annotations

import base64
import fnmatch
from typing import Any, cast

import httpx

GITHUB_API = "https://api.github.com"
# GitHub's contents API returns base64 up to ~1MB; refuse larger to keep
# responses bounded and avoid the separate blobs flow.
MAX_FILE_BYTES = 256 * 1024


def parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Parse a GitHub repo URL into (owner, repo).

    Accepts the common forms — ``https://github.com/owner/repo``,
    ``…/owner/repo.git``, ``git@github.com:owner/repo.git`` — and tolerates a
    trailing slash or extra path segments. Raises ``ValueError`` for anything
    that does not resolve to an owner/repo pair so form validation can reject it.
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
    if path.endswith(".git"):
        path = path[: -len(".git")]

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {repo_url!r}")
    return parts[0], parts[1]


class GitHubError(Exception):
    """Base error for GitHub API problems (carries a user-facing message)."""


class GitHubAuthError(GitHubError):
    """Authentication failed or the token lacks access to the repository."""


class GitHubNotFoundError(GitHubError):
    """Repository, ref, or path not found."""


class GitHubRateLimitError(GitHubError):
    """GitHub API rate limit exceeded."""


# ── glob filtering (shared by sync + tests) ──────────────────────────────────


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
    """Flatten a raw git tree into ``[{path, type, size}]`` applying scope filters.

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


# ── client ────────────────────────────────────────────────────────────────────


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
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                raise GitHubRateLimitError(
                    "GitHub API rate limit exceeded. Add an access token or try again later."
                )
            raise GitHubAuthError(
                "GitHub denied access. Check the repository URL and access token "
                "(private repositories require a token with read access)."
            )
        if resp.status_code == 404:
            raise GitHubNotFoundError(
                "Not found on GitHub (check the repository URL, branch, or path)."
            )
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Repository metadata (includes ``default_branch``)."""
        return cast(dict[str, Any], self._get(f"{GITHUB_API}/repos/{owner}/{repo}").json())

    def get_latest_release(self, owner: str, repo: str) -> dict[str, Any]:
        """Latest published, non-draft, non-prerelease release.

        Returns the subset the update check needs: ``{tag_name, html_url}``.
        Raises ``GitHubNotFoundError`` if the repo has no such release.
        """
        data = self._get(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest").json()
        return {"tag_name": data.get("tag_name", ""), "html_url": data.get("html_url", "")}

    def get_tree(self, owner: str, repo: str, ref: str) -> list[dict[str, Any]]:
        """Full recursive git tree for *ref* — raw entries ``[{path, type, size}]``."""
        resp = self._get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        data = resp.json()
        return data.get("tree", []) or []

    def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict[str, Any]:
        """Fetch a single file. Returns ``{path, size, text, truncated}``.

        Raises GitHubError for directories, binaries, or oversized files.
        """
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
        """Search code within a repo (default branch only). Returns path hits."""
        resp = self._get(
            f"{GITHUB_API}/search/code",
            params={"q": f"{query} repo:{owner}/{repo}", "per_page": str(limit)},
        )
        items = resp.json().get("items", []) or []
        return [{"path": it.get("path", "")} for it in items]
