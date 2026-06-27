"""HTTP client for the backend's internal service API.

The mutating tools (create_dashboard, add_chart, update_chart,
save_tether_graph) used to write to Postgres directly via SQLAlchemy. They now
POST/PATCH the backend's ``/api/internal/`` endpoints, which own the business
rules and the Django ORM writes. This keeps the MCP server free of any schema
coupling to Django.

Auth: a shared secret in the ``X-Service-Token`` header, matching the backend's
``INTERNAL_API_SERVICE_TOKEN``. Configure both via ``BACKEND_INTERNAL_API_URL``
and ``INTERNAL_API_SERVICE_TOKEN`` (see docker-compose.yml).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SERVICE_TOKEN_HEADER = "X-Service-Token"
_DEFAULT_BASE_URL = "http://backend:8000/api/internal"
_TIMEOUT_SECONDS = 30.0


def _base_url() -> str:
    return os.getenv("BACKEND_INTERNAL_API_URL", _DEFAULT_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("INTERNAL_API_SERVICE_TOKEN", "").strip()
    if token:
        headers[SERVICE_TOKEN_HEADER] = token
    return headers


async def call_internal(method: str, path: str, payload: dict[str, Any] | None = None) -> str:
    """Call an internal API endpoint and relay its JSON body as a string.

    The endpoints return the agent-facing ``{"success": ..., ...}`` shape on both
    success and handled errors, so the result is relayed verbatim to the tool's
    caller. Transport/decoding failures are wrapped in the same shape.
    """
    import httpx

    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, json=payload, headers=_headers())
    except httpx.HTTPError as exc:
        logger.error("Internal API %s %s failed: %s", method, path, exc, exc_info=True)
        return json.dumps({"success": False, "error": f"Internal API request failed: {exc}"})

    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        logger.error(
            "Internal API %s %s returned non-JSON (HTTP %s): %s",
            method,
            path,
            response.status_code,
            (response.text or "")[:200],
        )
        return json.dumps(
            {
                "success": False,
                "error": (
                    f"Internal API returned HTTP {response.status_code}: "
                    f"{(response.text or '')[:200]}"
                ),
            }
        )
    return json.dumps(body)
