"""HTTP helpers for talking to the MCP server from a consumer."""

from __future__ import annotations

import logging
import os
from pathlib import PurePosixPath

import httpx
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


async def _mcp_base_url() -> str:
    from ..models import SystemConfiguration

    return await database_sync_to_async(SystemConfiguration.get_value)(
        "mcp_base_url", ""
    ) or os.environ.get("MCP_BASE_URL", "http://mcp:8001")


async def read_mcp_resources(allowed_doc_sources: set[str] | None, uris: list[str]) -> str:
    """Read MCP resource contents by URI via the MCP server's HTTP endpoint.

    Validates URIs against the user's allowed doc sources before requesting.
    Returns a combined context string or empty string. ``allowed_doc_sources``
    of ``None`` means no role restriction (e.g. staff users).
    """
    mcp_base_url = await _mcp_base_url()
    parts: list[str] = []

    for uri in uris[:5]:  # cap at 5 resources per message
        if not isinstance(uri, str) or not uri.startswith("docs://"):
            continue

        rest = uri[len("docs://") :]
        source_name = rest.split("/", 1)[0] if "/" in rest else rest
        if allowed_doc_sources is not None and source_name not in allowed_doc_sources:
            continue

        params: dict[str, str] = {}
        if allowed_doc_sources is not None:
            params["allowed_doc_sources"] = ",".join(sorted(allowed_doc_sources))

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{mcp_base_url}/read-resource",
                    params={"uri": uri, **params},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content", "")
                if content:
                    file_path = rest.split("/", 1)[1] if "/" in rest else rest
                    suffix = PurePosixPath(file_path).suffix.lower()
                    if suffix and suffix != ".md":
                        lang = suffix.lstrip(".")
                        content = f"```{lang}\n{content}\n```"
                    parts.append(f"[Documentation: {uri}]\n{content}")
        except Exception:
            logger.warning("Failed to read MCP resource %s", uri, exc_info=True)
            parts.append(
                f"[Documentation: {uri}]\n"
                f"(Failed to load file content. The user referenced this file "
                f"but its contents could not be retrieved.)"
            )

    return "\n\n".join(parts)


async def fetch_tools_called(token: str | None = None) -> list[dict[str, object]]:
    """Fetch the tools called for this turn from the MCP server.

    Scoped by the request's filter ``token`` so concurrent turns don't read each
    other's tool calls. Returns an empty list when no token is available.
    """
    if not token:
        return []
    try:
        mcp_base_url = await _mcp_base_url()
        url = f"{mcp_base_url}/tools-called"
        logger.debug("Fetching tools from: %s", url)
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url, params={"token": token})
            resp.raise_for_status()
            data = resp.json()
            raw_tools = data.get("tools") or []
            result: list[dict[str, object]] = []
            for t in raw_tools:
                if isinstance(t, dict):
                    result.append(t)
            return result
    except Exception as e:
        logger.warning(f"Failed to fetch tools-called from MCP: {e}")
        return []
