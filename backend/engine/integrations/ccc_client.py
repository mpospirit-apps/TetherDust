"""HTTP client for the ccc (cocoindex-code) semantic-search service.

Backend side: used by the codebase sync task to (re)build the ccc index for
local codebases. The service is an internal FastAPI wrapper around the ``ccc``
CLI (see ``containers/ccc/``). Empty ``CCC_SERVICE_URL`` disables indexing (local
codebases remain browsable/readable; only semantic search is unavailable).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class CccError(Exception):
    """Raised when the ccc service is unreachable or returns an error."""


def _base_url() -> str:
    return os.getenv("CCC_SERVICE_URL", "").rstrip("/")


def _headers() -> dict[str, str]:
    secret = os.getenv("AGENT_GATEWAY_SECRET", "")
    return {"X-Gateway-Secret": secret} if secret else {}


def is_configured() -> bool:
    return bool(_base_url())


def index(project: str) -> dict[str, Any]:
    """Build/refresh the ccc index for a *project* path (relative to the ccc mount)."""
    base = _base_url()
    if not base:
        raise CccError("ccc service is not configured (CCC_SERVICE_URL unset).")
    try:
        resp = httpx.post(
            f"{base}/index",
            json={"project": project},
            headers=_headers(),
            timeout=600.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CccError(str(exc)) from exc
    result: dict[str, Any] = resp.json()
    return result
