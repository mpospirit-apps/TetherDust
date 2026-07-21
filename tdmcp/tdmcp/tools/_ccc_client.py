"""HTTP client for the ccc (cocoindex-code) semantic-search service.

Used by ``search_codebase`` to search local codebases. The service is an internal
FastAPI wrapper around the ``ccc`` CLI (see ``containers/ccc/``); it owns the
embedding model and the on-disk index. Empty ``CCC_SERVICE_URL`` disables local
code search (the tool then tells the agent to browse instead).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class CccError(Exception):
    """Raised when the ccc service is unreachable or returns an error."""


def _base_url() -> str:
    return os.environ.get("CCC_SERVICE_URL", "").rstrip("/")


def _headers() -> dict[str, str]:
    secret = os.environ.get("AGENT_GATEWAY_SECRET", "")
    return {"X-Gateway-Secret": secret} if secret else {}


def is_configured() -> bool:
    return bool(_base_url())


def search(project: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Semantic search within a ccc *project* path. Returns a list of hit dicts."""
    base = _base_url()
    if not base:
        raise CccError("ccc service is not configured (CCC_SERVICE_URL unset).")
    try:
        resp = httpx.post(
            f"{base}/search",
            json={"project": project, "query": query, "limit": limit},
            headers=_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CccError(str(exc)) from exc
    data = resp.json()
    results = data.get("results", [])
    return results if isinstance(results, list) else []
