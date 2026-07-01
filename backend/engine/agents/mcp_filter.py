"""Agent-agnostic MCP filter registration (Django side).

Per-request tool/database/doc-source/row-limit enforcement is implemented on
the MCP server via a token embedded in the MCP URL path: Django registers a
filter token, hands the agent a tokenized MCP URL, and the MCP server extracts
the token and hides/blocks disallowed tools for that request.

Registration used to live in `containers/codex/codex_api.py`, which made it
Codex-specific. It lives here now so every agent backend can reuse the same
handshake: call `register_filter(...)` to mint a token, embed it with
`tokenized_mcp_url(...)`, and `clear_filter(...)` on completion / error /
cancel (the MCP server's TTL is the safety net if the clear is missed).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def mcp_base_url() -> str:
    """Resolve the MCP server base URL (no trailing slash, no /mcp path)."""
    return os.getenv("MCP_BASE_URL", "http://tdmcp:8001").rstrip("/")


def _filter_auth_headers() -> dict[str, str]:
    """Shared-secret header authenticating filter registration with the MCP server.

    Empty when MCP_FILTER_SECRET is unset (enforcement disabled on both sides).
    """
    secret = os.getenv("MCP_FILTER_SECRET", "")
    return {"X-MCP-Filter-Secret": secret} if secret else {}


def tokenized_mcp_url(token: str, base_url: str | None = None) -> str:
    """Build the MCP URL an agent should connect to for a filtered request."""
    base = (base_url or mcp_base_url()).rstrip("/")
    return f"{base}/mcp/{token}"


def filter_needed(
    allowed_tools: list[str] | None,
    allowed_databases: list[str] | None,
    allowed_doc_sources: list[str] | None,
    max_row_limit: int | None,
    allowed_codebases: list[str] | None = None,
    allowed_reports: list[str] | None = None,
    allowed_dashboards: list[str] | None = None,
    allowed_tethers: list[str] | None = None,
) -> bool:
    """Whether any restriction is present and a filter token must be registered.

    `None` means "unrestricted" for each dimension; an empty list still means a
    restriction (deny-all) and must register a filter.
    """
    return (
        allowed_tools is not None
        or allowed_databases is not None
        or allowed_doc_sources is not None
        or allowed_codebases is not None
        or allowed_reports is not None
        or allowed_dashboards is not None
        or allowed_tethers is not None
        or max_row_limit is not None
    )


async def register_filter(
    allowed_tools: list[str] | None = None,
    allowed_databases: list[str] | None = None,
    allowed_doc_sources: list[str] | None = None,
    max_row_limit: int | None = None,
    allowed_codebases: list[str] | None = None,
    allowed_reports: list[str] | None = None,
    allowed_dashboards: list[str] | None = None,
    allowed_tethers: list[str] | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    base_url: str | None = None,
) -> str:
    """Register a filter with the MCP server and return its token.

    Raises the underlying ``httpx`` error on failure so the caller can surface a
    user-facing message and abort the request (failing closed).
    """
    token = str(uuid.uuid4())
    payload: dict[str, Any] = {"token": token}
    if allowed_tools is not None:
        payload["allowed_tools"] = allowed_tools
    if allowed_databases is not None:
        payload["allowed_databases"] = allowed_databases
    if allowed_doc_sources is not None:
        payload["allowed_doc_sources"] = allowed_doc_sources
    if allowed_codebases is not None:
        payload["allowed_codebases"] = allowed_codebases
    if allowed_reports is not None:
        payload["allowed_reports"] = allowed_reports
    if allowed_dashboards is not None:
        payload["allowed_dashboards"] = allowed_dashboards
    if allowed_tethers is not None:
        payload["allowed_tethers"] = allowed_tethers
    if max_row_limit is not None:
        payload["max_row_limit"] = max_row_limit
    if user_id is not None:
        payload["user_id"] = user_id
    if session_id is not None:
        payload["session_id"] = session_id

    base = (base_url or mcp_base_url()).rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base}/register-filter", json=payload, headers=_filter_auth_headers()
        )
        resp.raise_for_status()
    logger.debug(
        "Registered filter token %s — tools=%s, databases=%s, doc_sources=%s, "
        "codebases=%s, max_rows=%s, reports=%s, dashboards=%s, tethers=%s",
        token,
        allowed_tools,
        allowed_databases,
        allowed_doc_sources,
        allowed_codebases,
        max_row_limit,
        allowed_reports,
        allowed_dashboards,
        allowed_tethers,
    )
    return token


async def clear_filter(token: str, base_url: str | None = None) -> None:
    """Clear a registered filter (best-effort; the MCP server TTL is the backstop)."""
    if not token:
        return
    base = (base_url or mcp_base_url()).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.delete(f"{base}/clear-filter/{token}", headers=_filter_auth_headers())
        logger.info("Cleared filter token %s", token)
    except Exception:
        logger.warning("Failed to clear filter token %s (TTL will expire it)", token)
