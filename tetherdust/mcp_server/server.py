"""TetherDust MCP Server entry point.

Exposes database querying and documentation search tools via Model Context Protocol.
Supports three transports selected by MCP_TRANSPORT env var:
  - stdio (default): unfiltered local use (no RBAC — full access to every tool)
  - sse: HTTP/SSE mode (legacy)
  - streamable-http: Streamable HTTP mode for Docker service deployment. The
    Django/codex wrapper registers per-request token filters on this transport.
"""

import asyncio
import contextlib
import json as _json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import MCPResource, ReadResourceContents
from mcp.types import ContentBlock, TextContent, Tool

from . import __version__
from ._context import (
    request_allowed_codebases,
    request_allowed_dashboards,
    request_allowed_databases,
    request_allowed_doc_sources,
    request_allowed_reports,
    request_allowed_tethers,
    request_allowed_tools,
    request_filter_token,
    request_max_row_limit,
)
from .tools import register_tools

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))

# Shared secret that authenticates filter registration (Django → MCP). When set,
# /register-filter and /clear-filter require a matching X-MCP-Filter-Secret
# header, so a compromised agent process on the network can't mint or clear
# filter tokens for itself. When unset, enforcement is disabled (a startup
# warning is logged) — the shipped docker-compose sets it.
MCP_FILTER_SECRET = os.getenv("MCP_FILTER_SECRET", "")

log_level = os.getenv("TETHERDUST_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Track tool calls per request, keyed by the request's filter token, so
# concurrent chats don't read or clear each other's tool list. Each value is
# (tool_names, created_at); Django drains its token's entry via /tools-called
# after the turn, and a TTL purges any never-fetched entry.
_tool_calls_lock = threading.Lock()
_tool_calls_by_token: dict[str, tuple[list[str], float]] = {}
_TOOL_CALLS_TTL_SECONDS = int(os.getenv("TETHERDUST_TOOL_CALLS_TTL", "600"))


def _purge_expired_tool_calls() -> None:
    """Drop tool-call buffers whose turn never fetched them (TTL safety net)."""
    cutoff = time.time() - _TOOL_CALLS_TTL_SECONDS
    with _tool_calls_lock:
        stale = [tok for tok, (_, created) in _tool_calls_by_token.items() if created < cutoff]
        for tok in stale:
            del _tool_calls_by_token[tok]


def _record_tool_call(name: str) -> None:
    """Record a tool call under the current request's filter token (if any).

    Scoped to the token so concurrent requests don't share a buffer. Requests
    with no token (e.g. stdio transport) are not tracked — nothing fetches them.
    """
    token = request_filter_token.get()
    if not token:
        return
    with _tool_calls_lock:
        calls, _ = _tool_calls_by_token.setdefault(token, ([], time.time()))
        if name not in calls:
            calls.append(name)


def _drain_tool_calls(token: str) -> list[str]:
    """Return and remove the tools recorded for ``token`` (empty if unknown)."""
    with _tool_calls_lock:
        entry = _tool_calls_by_token.pop(token, None) if token else None
    return list(entry[0]) if entry else []


# Token-based filter registry:
#   {token: (allowed_tools, allowed_databases, allowed_doc_sources,
#            allowed_codebases, max_row_limit,
#            allowed_reports, allowed_dashboards, allowed_tethers, created_at)}
# Pre-registered by the Django agent layer before the CLI connects.
_registered_filters: dict[
    str,
    tuple[
        set[str] | None,
        set[str] | None,
        set[str] | None,
        set[str] | None,
        int | None,
        set[str] | None,
        set[str] | None,
        set[str] | None,
        float,
    ],
] = {}
_filters_lock = threading.Lock()
_FILTER_TTL_SECONDS = int(
    os.getenv("TETHERDUST_FILTER_TTL", "600")
)  # Auto-expire if DELETE never called


def _purge_expired_filters() -> None:
    """Remove filter entries older than TTL. Called on each MCP request."""
    now = time.time()
    with _filters_lock:
        expired = [
            tok
            for tok, (*_, created) in _registered_filters.items()
            if now - created > _FILTER_TTL_SECONDS
        ]
        for tok in expired:
            del _registered_filters[tok]
            logger.info("Purged expired filter for token %s", tok)


def _get_allowed_tools() -> set[str] | None:
    """Read allowed tools from the per-request context var (set by the token
    middleware). Returns None when no filter is registered — caller allows all.
    """
    return request_allowed_tools.get(None)


def _get_allowed_doc_sources() -> set[str] | None:
    """Read allowed doc sources from the per-request context var (set by the
    token middleware). Returns None when no filter is registered.
    """
    return request_allowed_doc_sources.get(None)


# Cached file index for /list-resources HTTP endpoint (not MCP protocol).
_doc_resources_cache: list[dict] = []
_doc_resources_cache_time: float = 0
_doc_resources_cache_lock = threading.Lock()
_DOC_RESOURCES_CACHE_TTL = 300  # seconds


def _build_doc_resources_index() -> list[dict]:
    """Walk all documentation sources and return metadata for every file."""
    from pathlib import Path

    from .tools import get_shared_parser

    parser = get_shared_parser()
    results: list[dict] = []
    for source in parser._sources:
        base = Path(source.path)
        if not base.is_dir():
            continue
        patterns = source.file_patterns if source.file_patterns else ["*.md"]
        matched: set[Path] = set()
        for pattern in patterns:
            matched.update(base.rglob(pattern))
        for doc_file in sorted(matched):
            rel = doc_file.relative_to(base)
            name = doc_file.stem if doc_file.suffix.lower() == ".md" else doc_file.name
            uri = f"docs://{source.name}/{rel}"
            results.append(
                {
                    "uri": uri,
                    "source_name": source.name,
                    "path": str(rel),
                    "name": name,
                }
            )
    return results


def _get_doc_resources_cached() -> list[dict]:
    """Return cached file index, rebuilding if stale or empty."""
    global _doc_resources_cache, _doc_resources_cache_time
    now = time.time()
    if _doc_resources_cache and (now - _doc_resources_cache_time) < _DOC_RESOURCES_CACHE_TTL:
        return _doc_resources_cache
    with _doc_resources_cache_lock:
        # Double-check after acquiring lock
        if _doc_resources_cache and (now - _doc_resources_cache_time) < _DOC_RESOURCES_CACHE_TTL:
            return _doc_resources_cache
        _doc_resources_cache = _build_doc_resources_index()
        _doc_resources_cache_time = time.time()
        logger.info("Rebuilt doc resources cache: %d files indexed", len(_doc_resources_cache))
        return _doc_resources_cache


def _list_doc_resources(
    allowed_sources: set[str] | None = None,
    query: str = "",
    limit: int = 30,
) -> list[dict]:
    """Return documentation resources, filtered by access and optional search query.

    Uses the cached file index. Results are capped at *limit*.
    """
    all_resources = _get_doc_resources_cached()

    # Filter by allowed sources
    if allowed_sources is not None:
        all_resources = [r for r in all_resources if r["source_name"] in allowed_sources]

    # Filter by search query (case-insensitive substring on name + path)
    if query:
        q = query.lower()
        all_resources = [
            r for r in all_resources if q in r["name"].lower() or q in r["path"].lower()
        ]

    return all_resources[:limit]


class TetherDustMCP(FastMCP):
    """FastMCP server with role-based tool/resource filtering and call tracking."""

    async def list_tools(self) -> list[Tool]:
        tools = await super().list_tools()
        allowed = _get_allowed_tools()
        if allowed is not None:
            tools = [t for t in tools if t.name in allowed]
        return tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        allowed = _get_allowed_tools()
        if allowed is not None and name not in allowed:
            return [TextContent(type="text", text=f"Tool '{name}' is not available for your role.")]

        _record_tool_call(name)

        return await super().call_tool(name, arguments)

    async def list_resources(self) -> list[MCPResource]:
        """List documentation files as MCP resources, filtered by role."""
        allowed_sources = _get_allowed_doc_sources()
        docs = _list_doc_resources(allowed_sources)
        resources = []
        for doc in docs:
            is_md = doc["path"].lower().endswith(".md")
            resources.append(
                MCPResource(
                    uri=doc["uri"],
                    name=doc["name"],
                    description=f"Documentation file from {doc['source_name']}: {doc['path']}",
                    mimeType="text/markdown" if is_md else "text/plain",
                )
            )
        return resources

    async def read_resource(self, uri: object) -> list[ReadResourceContents]:
        """Read a documentation file by its docs:// URI, enforcing role access."""
        from pathlib import Path

        uri_str = str(uri)
        if not uri_str.startswith("docs://"):
            return await super().read_resource(uri)

        # Parse docs://{source_name}/{path}
        rest = uri_str[len("docs://") :]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid docs URI: {uri_str}")
        source_name, file_path = parts

        # Enforce role access
        allowed_sources = _get_allowed_doc_sources()
        if allowed_sources is not None and source_name not in allowed_sources:
            raise ValueError(
                f"Access denied: source '{source_name}' is not available for your role."
            )

        # Resolve file path
        from .tools import get_shared_parser

        parser = get_shared_parser()
        for source in parser._sources:
            if source.name == source_name:
                base = Path(source.path)
                target = (base / file_path).resolve()
                # Path traversal protection
                if not target.is_relative_to(base.resolve()):
                    raise ValueError("Invalid file path.")
                if not target.is_file():
                    raise ValueError(f"File not found: {file_path}")
                content = target.read_text(encoding="utf-8")
                is_md = target.suffix.lower() == ".md"
                mime = "text/markdown" if is_md else "text/plain"
                return [ReadResourceContents(content=content, mime_type=mime)]
        raise ValueError(f"Source not found: {source_name}")


mcp = TetherDustMCP("tetherdust", host=MCP_HOST, port=MCP_PORT)
register_tools(mcp)


# ── Shared HTTP helpers ──────────────────────────────────────────────────────


async def _tools_called_handler(request: Any) -> Any:
    """Return and clear the tools called for one request, identified by its token.

    Requires a ``?token=`` matching the request's MCP filter token, so a turn
    only ever sees its own tool calls. Without a token (or an unknown one) the
    response is empty.
    """
    from starlette.responses import JSONResponse

    _purge_expired_tool_calls()
    token = request.query_params.get("token", "")
    tools = _drain_tool_calls(token)
    return JSONResponse({"tools": tools})


async def _list_resources_handler(request: Any) -> Any:
    """Return documentation resources, filtered by access and optional search query.

    Query params:
      - allowed_doc_sources: comma-separated source names for access control
      - q: search query (case-insensitive substring match on name/path)
    """
    from starlette.responses import JSONResponse

    allowed_param = request.query_params.get("allowed_doc_sources")
    allowed_sources = None
    if allowed_param:
        allowed_sources = {s.strip() for s in allowed_param.split(",") if s.strip()}
    query = request.query_params.get("q", "").strip()
    docs = _list_doc_resources(allowed_sources, query=query)
    return JSONResponse({"resources": docs})


async def _read_resource_handler(request: Any) -> Any:
    """Read a single MCP resource by URI, with optional doc source filtering."""
    from starlette.responses import JSONResponse

    uri = request.query_params.get("uri", "")
    if not uri:
        return JSONResponse({"error": "uri parameter is required"}, status_code=400)

    # Parse allowed sources from query params for access control
    allowed_param = request.query_params.get("allowed_doc_sources")
    if allowed_param:
        allowed_sources = {s.strip() for s in allowed_param.split(",") if s.strip()}
        ctx_docs = request_allowed_doc_sources.set(allowed_sources)
    else:
        ctx_docs = request_allowed_doc_sources.set(None)

    try:
        results = await mcp.read_resource(uri)
        content = results[0].content if results else ""
        return JSONResponse({"content": content, "uri": uri})
    except (ValueError, Exception) as e:
        return JSONResponse({"error": str(e), "uri": uri}, status_code=403)
    finally:
        request_allowed_doc_sources.reset(ctx_docs)


async def _healthz(request: Any) -> Any:
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


# ── stdio transport ──────────────────────────────────────────────────────────


async def main() -> None:
    """Run the MCP server using stdio transport."""
    logger.info("Starting TetherDust MCP Server v%s [stdio]", __version__)
    await mcp.run_stdio_async()


# ── SSE transport (legacy) ───────────────────────────────────────────────────


def _build_sse_app() -> object:
    """Build a Starlette ASGI app that serves MCP over HTTP/SSE transport."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    sse_app = mcp.sse_app()

    # Wrap the SSE app with additional utility routes
    return Starlette(
        routes=[
            Route("/healthz", _healthz),
            Route("/tools-called", _tools_called_handler),
            Route("/list-resources", _list_resources_handler),
            Route("/read-resource", _read_resource_handler),
            Route("/{path:path}", sse_app, methods=["GET", "POST"]),
        ],
    )


def _run_sse() -> None:
    """Run the MCP server using HTTP/SSE transport (blocking)."""
    import uvicorn

    logger.info(
        "Starting TetherDust MCP Server v%s [sse] on %s:%s",
        __version__,
        MCP_HOST,
        MCP_PORT,
    )
    uvicorn.run(_build_sse_app(), host=MCP_HOST, port=MCP_PORT)


# ── Streamable HTTP transport ────────────────────────────────────────────────


def _build_streamable_http_app() -> object:
    """Build a Starlette ASGI app that serves MCP over Streamable HTTP transport.

    The MCP endpoint is mounted at /mcp and supports optional token-based
    tool filtering via path: /mcp/<token>.  Tokens are pre-registered by
    codex_api.py via POST /register-filter before spawning the Codex CLI.
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount, Route
    from starlette.types import Receive, Scope, Send

    session_manager = StreamableHTTPSessionManager(app=mcp._mcp_server)

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        _purge_expired_filters()

        path = scope.get("path", "/")
        clean = path.lstrip("/")
        if clean.startswith("mcp/"):
            clean = clean[len("mcp/") :]
        elif clean == "mcp":
            clean = ""
        token_str = clean.split("/")[0] if clean else ""

        # Fail closed: every streamable-http request must carry a registered
        # token. A bare /mcp request (no token) is rejected rather than granted
        # unrestricted access, so an agent that can reach this endpoint over the
        # network cannot bypass its role's filter by dropping the token. The
        # Django agent layer always registers a token before connecting —
        # including an all-access token for unrestricted/staff requests.
        with _filters_lock:
            entry = _registered_filters.get(token_str) if token_str else None
        if entry is None:
            response = Response(
                content=_json.dumps({"error": "Unknown or expired filter token"}),
                status_code=403,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return
        (
            allowed_tools,
            allowed_dbs,
            allowed_docs,
            allowed_cbs,
            max_rows,
            allowed_reports,
            allowed_dashboards,
            allowed_tethers,
            _,
        ) = entry
        ctx_tools = request_allowed_tools.set(allowed_tools)
        ctx_dbs = request_allowed_databases.set(allowed_dbs)
        ctx_docs = request_allowed_doc_sources.set(allowed_docs)
        ctx_cbs = request_allowed_codebases.set(allowed_cbs)
        ctx_rows = request_max_row_limit.set(max_rows)
        ctx_token = request_filter_token.set(token_str)
        ctx_reports = request_allowed_reports.set(allowed_reports)
        ctx_dashboards = request_allowed_dashboards.set(allowed_dashboards)
        ctx_tethers = request_allowed_tethers.set(allowed_tethers)

        scope["path"] = "/"

        try:
            await session_manager.handle_request(scope, receive, send)
        finally:
            request_allowed_tools.reset(ctx_tools)
            request_allowed_databases.reset(ctx_dbs)
            request_allowed_doc_sources.reset(ctx_docs)
            request_allowed_codebases.reset(ctx_cbs)
            request_max_row_limit.reset(ctx_rows)
            request_filter_token.reset(ctx_token)
            request_allowed_reports.reset(ctx_reports)
            request_allowed_dashboards.reset(ctx_dashboards)
            request_allowed_tethers.reset(ctx_tethers)

    def _filter_secret_ok(request: Request) -> bool:
        """Validate the shared secret on filter-management requests.

        Enforced only when MCP_FILTER_SECRET is configured. Returns True when
        enforcement is disabled so local/dev setups keep working.
        """
        if not MCP_FILTER_SECRET:
            return True
        return request.headers.get("x-mcp-filter-secret", "") == MCP_FILTER_SECRET

    async def register_filter(request: Request) -> Response:
        if not _filter_secret_ok(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        body = await request.json()
        token_str = body.get("token", "")
        if not token_str:
            return JSONResponse({"error": "token is required"}, status_code=400)
        tools_set = set(body["allowed_tools"]) if body.get("allowed_tools") is not None else None
        dbs_set = (
            set(body["allowed_databases"]) if body.get("allowed_databases") is not None else None
        )
        docs_set = (
            set(body["allowed_doc_sources"])
            if body.get("allowed_doc_sources") is not None
            else None
        )
        cbs_set = (
            set(body["allowed_codebases"]) if body.get("allowed_codebases") is not None else None
        )
        max_rows = int(body["max_row_limit"]) if body.get("max_row_limit") is not None else None
        reports_set = (
            set(body["allowed_reports"]) if body.get("allowed_reports") is not None else None
        )
        dashboards_set = (
            set(body["allowed_dashboards"]) if body.get("allowed_dashboards") is not None else None
        )
        tethers_set = (
            set(body["allowed_tethers"]) if body.get("allowed_tethers") is not None else None
        )
        with _filters_lock:
            _registered_filters[token_str] = (
                tools_set,
                dbs_set,
                docs_set,
                cbs_set,
                max_rows,
                reports_set,
                dashboards_set,
                tethers_set,
                time.time(),
            )
        logger.info(
            "Registered filter for token %s: tools=%s, databases=%s, doc_sources=%s, "
            "codebases=%s, max_rows=%s, reports=%s, dashboards=%s, tethers=%s",
            token_str,
            sorted(tools_set) if tools_set is not None else None,
            sorted(dbs_set) if dbs_set else None,
            sorted(docs_set) if docs_set else None,
            sorted(cbs_set) if cbs_set else None,
            max_rows,
            sorted(reports_set) if reports_set else None,
            sorted(dashboards_set) if dashboards_set else None,
            sorted(tethers_set) if tethers_set else None,
        )
        return JSONResponse({"status": "registered", "token": token_str})

    async def clear_filter(request: Request) -> Response:
        if not _filter_secret_ok(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        token_str = request.path_params["token"]
        with _filters_lock:
            removed = _registered_filters.pop(token_str, None)
        if removed:
            logger.info("Cleared filter for token %s", token_str)
        return JSONResponse({"status": "cleared"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("Streamable HTTP session manager started")
            # Pre-warm the doc resources cache in the background so the first
            # /list-resources request doesn't have to wait for the full file walk.
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, _get_doc_resources_cached)
            yield

    return Starlette(
        routes=[
            Route("/healthz", _healthz),
            Route("/tools-called", _tools_called_handler),
            Route("/list-resources", _list_resources_handler),
            Route("/read-resource", _read_resource_handler),
            Route("/register-filter", register_filter, methods=["POST"]),
            Route("/clear-filter/{token}", clear_filter, methods=["DELETE"]),
            Mount("/mcp", app=handle_mcp),
        ],
        lifespan=lifespan,
    )


def _run_streamable_http() -> None:
    """Run the MCP server using Streamable HTTP transport (blocking)."""
    import uvicorn

    logger.info(
        "Starting TetherDust MCP Server v%s [streamable-http] on %s:%s",
        __version__,
        MCP_HOST,
        MCP_PORT,
    )
    if not MCP_FILTER_SECRET:
        logger.warning(
            "MCP_FILTER_SECRET is not set — filter registration is UNAUTHENTICATED. "
            "Set it (and the matching value on the web/celery services) before any "
            "non-development use."
        )
    uvicorn.run(_build_streamable_http_app(), host=MCP_HOST, port=MCP_PORT)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        _run_streamable_http()
    elif transport == "sse":
        _run_sse()
    else:
        asyncio.run(main())
