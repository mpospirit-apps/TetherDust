"""Local MCP proxy service.

Manages subprocess-based MCP servers (stdio transport) and exposes them over
streamable-http at POST /mcp/{server_id}/.

Each configured MCPServerConfiguration row with a non-empty `command` gets its
own persistent ClientSession connected to a subprocess. Incoming HTTP requests
are forwarded to the appropriate subprocess and the response is returned as JSON.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DATABASE_URL = os.getenv("DATABASE_URL", "")
ENCRYPTION_KEY = os.getenv("TETHERDUST_ENCRYPTION_KEY", "")
LOCAL_MCP_PORT = int(os.getenv("LOCAL_MCP_PORT", "8003"))

# {server_id: _ServerProxy} — IDs are prefixed strings, e.g. "mcp_af30…".
_proxies: dict[str, "_ServerProxy"] = {}
_proxies_lock = asyncio.Lock()


def _decrypt(encrypted: str) -> str:
    if not encrypted or not ENCRYPTION_KEY:
        return ""
    try:
        key = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
        # Fernet key must be 32 url-safe base64 bytes
        f = Fernet(key)
        return f.decrypt(encrypted.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def _load_servers() -> list[dict[str, Any]]:
    """Read local MCP server configs from PostgreSQL."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set; no local MCP servers loaded.")
        return []

    # Strip SQLAlchemy driver prefix if present
    dsn = DATABASE_URL
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix) :]
            break

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, command, args, command_env
            FROM engine_mcpserverconfiguration
            WHERE is_active = TRUE AND is_builtin = FALSE AND command <> ''
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.error("Failed to load servers from DB: %s", exc)
        return []

    servers = []
    for row_id, name, command, args_raw, env_encrypted in rows:
        env_json = _decrypt(env_encrypted) if env_encrypted else ""
        try:
            env = json.loads(env_json) if env_json else {}
        except Exception:
            env = {}
        if isinstance(args_raw, str):
            try:
                args: list[str] = [str(a) for a in json.loads(args_raw)]
            except Exception:
                args = []
        else:
            args = [str(a) for a in args_raw] if args_raw else []
        servers.append({"id": row_id, "name": name, "command": command, "args": args, "env": env})

    logger.info("Loaded %d local MCP server(s) from DB.", len(servers))
    return servers


class _ServerProxy:
    """Manages a persistent ClientSession for one subprocess-based MCP server."""

    def __init__(
        self, server_id: str, name: str, command: str, args: list[str], env: dict[str, str]
    ):
        self.server_id = server_id
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self._task: asyncio.Task[None] | None = None
        self._session: ClientSession | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self.last_error: str | None = None
        self.state: str = "pending"  # pending | starting | ready | failed | stopped

    async def start(self) -> None:
        self.state = "starting"
        self.last_error = None
        self._ready.clear()
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"proxy-{self.server_id}")

    async def stop(self) -> None:
        self.state = "stopped"
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._session = None
        self._ready.clear()

    async def _run(self) -> None:
        merged_env = {**os.environ, **self.env}
        path_in_use = merged_env.get("PATH", "<not set>")

        # Support users who paste the full command string into the command field
        # e.g. "npx @modelcontextprotocol/server-notion" instead of command=npx args=[...]
        parts = self.command.split()
        executable = parts[0]
        extra_args = parts[1:]
        effective_args = extra_args + list(self.args)
        cmd_str = f"{executable} {' '.join(effective_args)}"

        # Resolve the executable so we can give a clear error before even trying
        resolved = shutil.which(executable, path=merged_env.get("PATH"))
        if resolved is None:
            self.last_error = f"Command {executable!r} not found in PATH. PATH={path_in_use}"
            self.state = "failed"
            logger.error("[%s] %s", self.name, self.last_error)
            return

        logger.info("[%s] Starting subprocess: %s (resolved=%s)", self.name, cmd_str, resolved)
        logger.info("[%s] PATH=%s", self.name, path_in_use)

        # Capture subprocess stderr so we can surface the real failure reason
        # (missing npm package, bad API key, traceback, etc.) instead of a bare
        # "McpError: Connection closed" when the child dies during init.
        stderr_capture = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")

        def _read_stderr_tail(limit: int = 2000) -> str:
            try:
                stderr_capture.flush()
                stderr_capture.seek(0)
                text = stderr_capture.read().strip()
            except Exception:
                return ""
            if len(text) > limit:
                text = "…" + text[-limit:]
            return text

        params = StdioServerParameters(command=executable, args=effective_args, env=merged_env)
        try:
            async with stdio_client(params, errlog=stderr_capture) as (read_stream, write_stream):
                logger.info("[%s] Subprocess started, initializing MCP session...", self.name)
                async with ClientSession(read_stream, write_stream) as session:
                    logger.info("[%s] Sending initialize handshake...", self.name)
                    init_result = await session.initialize()
                    server_info = getattr(init_result, "serverInfo", None)
                    logger.info("[%s] MCP session ready. serverInfo=%r", self.name, server_info)
                    self._session = session
                    self.state = "ready"
                    self._ready.set()
                    await self._stop.wait()
        except asyncio.CancelledError:
            self.state = "stopped"
        except FileNotFoundError as exc:
            self.last_error = (
                f"Command {executable!r} not found (FileNotFoundError). "
                f"Resolved path: {resolved}. PATH={path_in_use}. Detail: {exc}"
            )
            self.state = "failed"
            logger.error("[%s] %s", self.name, self.last_error)
        except BaseException as exc:
            # Unwrap ExceptionGroup (Python 3.11+ / anyio TaskGroup) to surface the real error
            real = exc
            if isinstance(exc, BaseExceptionGroup):
                flat = list(exc.exceptions)
                while flat:
                    e = flat.pop(0)
                    if isinstance(e, BaseExceptionGroup):
                        flat.extend(e.exceptions)
                    else:
                        real = e
                        break
            stderr_tail = _read_stderr_tail()
            base_msg = f"{type(real).__name__}: {real}"
            if stderr_tail:
                self.last_error = f"{base_msg}\n--- subprocess stderr ---\n{stderr_tail}"
            else:
                self.last_error = (
                    f"{base_msg} (subprocess produced no stderr — the command may have "
                    f"exited immediately. Verify {executable!r} {effective_args!r} runs as "
                    f"an MCP stdio server.)"
                )
            self.state = "failed"
            logger.error("[%s] Subprocess failed: %s", self.name, self.last_error, exc_info=True)
        finally:
            try:
                stderr_capture.close()
            except Exception:
                pass
            self._session = None
            self._ready.clear()
            logger.info("[%s] Subprocess exited (state=%s).", self.name, self.state)

    async def get_session(self, timeout: float = 120.0) -> ClientSession:
        if self.state == "failed":
            raise RuntimeError(f"MCP server {self.name!r} failed to start: {self.last_error}")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError:
            raise RuntimeError(
                f"MCP server {self.name!r} did not become ready within {timeout}s "
                f"(state={self.state}, last_error={self.last_error!r})"
            )
        if self._session is None:
            raise RuntimeError(
                f"MCP server {self.name!r} session is not available (state={self.state})"
            )
        return self._session


async def _sync_proxies(servers: list[dict[str, Any]]) -> None:
    """Start proxies for new servers, stop proxies for removed servers."""
    async with _proxies_lock:
        desired_ids = {s["id"] for s in servers}
        current_ids = set(_proxies.keys())

        # Stop removed
        for sid in current_ids - desired_ids:
            proxy = _proxies.pop(sid)
            logger.info("Stopping removed server proxy: %r", proxy.name)
            await proxy.stop()

        # Start new
        for s in servers:
            if s["id"] not in _proxies:
                proxy = _ServerProxy(s["id"], s["name"], s["command"], s["args"], s["env"])
                _proxies[s["id"]] = proxy
                await proxy.start()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    servers = _load_servers()
    await _sync_proxies(servers)
    yield
    async with _proxies_lock:
        for proxy in list(_proxies.values()):
            await proxy.stop()
        _proxies.clear()


app = FastAPI(title="TetherDust Local MCP Proxy", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "servers": len(_proxies)}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Return the state of every managed proxy."""
    return {
        "servers": [
            {
                "id": p.server_id,
                "name": p.name,
                "command": f"{p.command} {' '.join(p.args)}",
                "state": p.state,
                "last_error": p.last_error,
            }
            for p in _proxies.values()
        ]
    }


@app.post("/reload")
async def reload() -> dict[str, Any]:
    """Re-read DB and sync running proxies."""
    servers = _load_servers()
    logger.info("Reload requested — syncing %d server(s) from DB.", len(servers))
    await _sync_proxies(servers)
    return {
        "ok": True,
        "servers": [
            {"id": p.server_id, "name": p.name, "state": p.state} for p in _proxies.values()
        ],
    }


@app.post("/mcp/{server_id}/", response_model=None)
async def proxy_mcp(server_id: str, request: Request) -> Response | JSONResponse:
    """Proxy a single MCP JSON-RPC request to the appropriate subprocess."""
    async with _proxies_lock:
        proxy = _proxies.get(server_id)

    if proxy is None:
        raise HTTPException(
            status_code=404, detail=f"No active local MCP server with id={server_id}"
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    method = body.get("method", "")
    params = body.get("params") or {}
    req_id = body.get("id", str(uuid.uuid4()))

    logger.info("[%s] → %s (state=%s)", proxy.name, method, proxy.state)

    # Notifications are fire-and-forget — MCP streamable-http spec requires 202 with no body.
    if method.startswith("notifications/"):
        return Response(status_code=202)

    try:
        session = await proxy.get_session()
    except RuntimeError as exc:
        logger.error("[%s] get_session failed: %s", proxy.name, exc)
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}}
        )

    try:
        result = await _dispatch(session, method, params)
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
    except Exception as exc:
        logger.error("Error dispatching %s for server %s: %s", method, server_id, exc)
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}}
        )


async def _dispatch(session: ClientSession, method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        init_result = await session.initialize()
        return {
            "protocolVersion": getattr(init_result, "protocolVersion", "2024-11-05"),
            "capabilities": _to_dict(getattr(init_result, "capabilities", {})),
            "serverInfo": _to_dict(getattr(init_result, "serverInfo", {})),
        }

    if method == "tools/list":
        tools_result = await session.list_tools()
        tools = tools_result.tools if hasattr(tools_result, "tools") else []
        return {"tools": [_tool_to_dict(t) for t in tools]}

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        call_result = await session.call_tool(name, arguments)
        return _call_result_to_dict(call_result)

    if method == "prompts/list":
        prompts_result = await session.list_prompts()
        prompts = prompts_result.prompts if hasattr(prompts_result, "prompts") else []
        return {"prompts": [_to_dict(p) for p in prompts]}

    if method == "prompts/get":
        prompt_result = await session.get_prompt(params.get("name", ""), params.get("arguments"))
        return _to_dict(prompt_result)

    if method == "resources/list":
        resources_result = await session.list_resources()
        resources = resources_result.resources if hasattr(resources_result, "resources") else []
        return {"resources": [_to_dict(r) for r in resources]}

    if method == "ping":
        await session.send_ping()
        return {}

    raise ValueError(f"Unsupported MCP method: {method!r}")


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", ""),
        "inputSchema": _to_dict(getattr(tool, "inputSchema", {})),
    }


def _call_result_to_dict(result: Any) -> dict[str, Any]:
    content = getattr(result, "content", [])
    return {
        "content": [_to_dict(c) for c in content],
        "isError": getattr(result, "isError", False),
    }


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)
