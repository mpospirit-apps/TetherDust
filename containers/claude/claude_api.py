"""Thin FastAPI wrapper around the Claude Code CLI subprocess.

The mirror of ``containers/codex/codex_api.py`` for Claude Code. It exposes the same
contract to Django so :class:`engine.agents.claude.ClaudeCodeAgent` (a subclass of
``CodexAgent``) can talk to it unchanged:

  POST /chat              — stream the CLI response as SSE
  POST /abort/{session}   — terminate a running CLI subprocess
  POST /update-agents-md  — store the system prompt (fallback to per-request one)
  GET  /healthz           — liveness probe

Differences from the Codex gateway:

* **Auth** — Claude Code authenticates with a long-lived OAuth token (from
  ``claude setup-token`` on a Claude Pro/Max subscription), injected per request
  as the ``CLAUDE_CODE_OAUTH_TOKEN`` env var. There is no auth.json to seed or
  refresh, so the volume/seed/harvest machinery the Codex gateway needs is gone.
* **MCP config** — Claude Code is configured with a ``--mcp-config`` JSON blob
  and ``--allowedTools``, not a TOML config dir. The pre-tokenized ``mcp_url``
  Django supplies (for role-restricted requests) goes straight into that JSON.
* **Stream format** — the CLI emits ``--output-format stream-json``; this module
  translates those events into the same ``{type: tool_call|text|thinking|
  response|error_detail}`` SSE events the Codex gateway emits.

Per-request tool filtering is still enforced on the MCP server via the token in
the ``mcp_url`` path; Django registers and clears it. Built-in CLI tools (Bash,
file edits) are *not* granted — ``--allowedTools`` is scoped to the MCP servers
only, so every tool the model can reach is an MCP tool subject to role filters.
"""

import asyncio
import fcntl
import json
import logging
import os
import pty
import re
import select
import struct
import subprocess
import termios
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Shared secret authenticating Django → gateway calls. The gateway sits on the
# internal Docker network with no user-facing auth; when set, every endpoint
# except /healthz requires a matching X-Gateway-Secret header so a process that
# can reach the gateway can't drive the agent with attacker-chosen credentials.
# Unset disables enforcement (a startup warning is logged) for local/dev use.
GATEWAY_SECRET = os.getenv("AGENT_GATEWAY_SECRET", "")

if not GATEWAY_SECRET:
    logger.warning(
        "AGENT_GATEWAY_SECRET is not set — the Claude gateway is UNAUTHENTICATED. "
        "Set it (and the matching value on the web/celery services) before any "
        "non-development use."
    )


def _require_gateway_secret(x_gateway_secret: str | None = Header(default=None)) -> None:
    """FastAPI dependency: reject requests missing the shared secret (when set)."""
    if GATEWAY_SECRET and x_gateway_secret != GATEWAY_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="TetherDust Claude Code API")

# Track active subprocesses by session_id for explicit abort.
_active_processes: dict[str, asyncio.subprocess.Process] = {}

CLAUDE_COMMAND = os.getenv("CLAUDE_COMMAND", "claude")
# Default MCP URL for unrestricted requests (no filter token). Restricted
# requests receive a pre-tokenized `mcp_url` from Django instead.
MCP_URL = os.getenv("MCP_URL", "http://tdmcp:8001/mcp")
# Writable config/home dir for the CLI (keeps it off /root). OAuth auth is via
# env var, so nothing sensitive is persisted here.
CLAUDE_CONFIG_DIR = Path(os.getenv("CLAUDE_CONFIG_DIR", "/var/claude-home/.claude"))
CLAUDE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
# Neutral, empty working directory so the CLI never treats a real repo as the
# project context (it would otherwise try to read files we don't want it to).
CLAUDE_WORKDIR = Path(os.getenv("CLAUDE_WORKDIR", "/var/claude-home/work"))
CLAUDE_WORKDIR.mkdir(parents=True, exist_ok=True)
# Stored system prompt (fallback when a request carries no `instructions`).
AGENTS_MD_PATH = Path("/app/CLAUDE.md")


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: int
    allowed_tools: list[str] | None = None
    allowed_databases: list[str] | None = None
    allowed_doc_sources: list[str] | None = None
    max_row_limit: str | None = None
    # Claude Code OAuth token (subscription auth). Injected as an env var.
    auth_token: str | None = None
    # Anthropic API key (per-token billing). Injected as the ANTHROPIC_API_KEY
    # env var for the subprocess and takes precedence over auth_token when both
    # are present. `claude -p` reads it as the X-Api-Key header.
    api_key: str | None = None
    instructions: str | None = None
    # Model name as Claude Code expects it (e.g. "sonnet", "opus",
    # "claude-sonnet-4-5"). Blank → the CLI/subscription default.
    model: str | None = None
    # Accepted for parity with the Codex gateway; Claude Code has no equivalent
    # reasoning-effort knob, so it is ignored.
    reasoning_effort: str | None = None
    # Pre-tokenized MCP URL for the built-in tetherdust server (restricted
    # requests). Absent → unrestricted (the default MCP_URL is used).
    mcp_url: str | None = None
    # Extra MCP servers the caller's role allows. Each entry has keys `name`,
    # `url`, `transport`, `auth_token`, `headers`.
    custom_mcp_servers: list[dict[str, Any]] | None = None


_RESERVED_MCP_KEYS = {"tetherdust"}


def _sanitize_mcp_key(name: str) -> str:
    """Derive a safe MCP server key from a human-friendly name."""
    key = re.sub(r"[^a-z0-9_]+", "_", (name or "").strip().lower()).strip("_")
    if not key:
        key = "server"
    if key in _RESERVED_MCP_KEYS:
        key = f"{key}_custom"
    return key


def _build_mcp_config(
    mcp_url: str | None,
    custom_mcp_servers: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Build the `--mcp-config` JSON and the list of allowed MCP tool prefixes.

    Returns ``(config_dict, allowed_prefixes)`` where ``config_dict`` is the
    ``{"mcpServers": {...}}`` blob and ``allowed_prefixes`` are the
    ``mcp__<server>`` strings to pass to ``--allowedTools`` (which grants every
    tool exposed by that server — the MCP server itself enforces the role's
    per-tool filter via the token in the URL).
    """
    servers: dict[str, dict[str, Any]] = {
        "tetherdust": {"type": "http", "url": mcp_url or MCP_URL},
    }
    allowed: list[str] = ["mcp__tetherdust"]

    used = set(_RESERVED_MCP_KEYS)
    for server in custom_mcp_servers or []:
        url = (server.get("url") or "").strip()
        if not url:
            continue
        base_key = _sanitize_mcp_key(server.get("name") or "server")
        key = base_key
        suffix = 2
        while key in used:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used.add(key)

        transport = (server.get("transport") or "http").strip().lower()
        entry: dict[str, Any] = {
            "type": "sse" if transport == "sse" else "http",
            "url": url,
        }
        headers: dict[str, str] = dict(server.get("headers") or {})
        auth_token = (server.get("auth_token") or "").strip()
        if auth_token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {auth_token}"
        if headers:
            entry["headers"] = headers
        servers[key] = entry
        allowed.append(f"mcp__{key}")

    return {"mcpServers": servers}, allowed


def _redact_servers_for_log(servers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not servers:
        return []
    redacted = []
    for s in servers:
        copy = {k: v for k, v in s.items() if k not in ("auth_token", "headers")}
        if s.get("auth_token"):
            copy["auth_token"] = "***"
        if s.get("headers"):
            copy["headers"] = {k: "***" for k in s["headers"]}
        redacted.append(copy)
    return redacted


def _resolve_instructions(request: ChatRequest) -> str:
    """Per-request instructions win; otherwise fall back to the stored CLAUDE.md."""
    if request.instructions and request.instructions.strip():
        return request.instructions.strip()
    if AGENTS_MD_PATH.exists():
        try:
            return AGENTS_MD_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _tool_display_name(raw: str) -> str:
    """`mcp__tetherdust__query_database` → `query_database` (parity with Codex)."""
    if raw.startswith("mcp__"):
        return raw.split("__")[-1]
    return raw


async def _stream_claude(request: ChatRequest) -> AsyncIterator[str]:
    """Spawn a Claude Code CLI subprocess and yield SSE-formatted chunks."""
    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = str(CLAUDE_CONFIG_DIR)
    env["HOME"] = str(CLAUDE_CONFIG_DIR.parent)
    # Auth: an API key (per-token billing) takes precedence over the OAuth
    # subscription token. Inject the chosen credential for this one subprocess
    # only and clear the other so a stray env var can't shadow it.
    if request.api_key:
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        env["ANTHROPIC_API_KEY"] = request.api_key
    else:
        env.pop("ANTHROPIC_API_KEY", None)
        if request.auth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = request.auth_token

    if request.allowed_databases is not None:
        env["TETHERDUST_ALLOWED_DATABASES"] = ",".join(request.allowed_databases)
    if request.allowed_doc_sources is not None:
        env["TETHERDUST_ALLOWED_DOC_SOURCES"] = ",".join(request.allowed_doc_sources)
    if request.max_row_limit:
        env["TETHERDUST_MAX_ROW_LIMIT"] = request.max_row_limit

    mcp_config, allowed_prefixes = _build_mcp_config(request.mcp_url, request.custom_mcp_servers)

    logger.debug(
        "Received request: allowed_tools=%s, allowed_databases=%s, "
        "allowed_doc_sources=%s, max_row_limit=%s, model=%s, mcp_url=%s, "
        "custom_mcp_servers=%s",
        request.allowed_tools,
        request.allowed_databases,
        request.allowed_doc_sources,
        request.max_row_limit,
        request.model,
        "<tokenized>" if request.mcp_url else None,
        _redact_servers_for_log(request.custom_mcp_servers),
    )

    cmd = [
        CLAUDE_COMMAND,
        "-p",  # print / headless mode (non-interactive)
        "--output-format",
        "stream-json",
        "--verbose",  # required for stream-json in print mode
        "--include-partial-messages",  # token-level deltas for the typing effect
        "--mcp-config",
        json.dumps(mcp_config),
        # Scope tool access to the MCP servers only — no built-in Bash/file tools.
        # Disallowed tool calls are auto-denied in headless mode (no prompt hang).
        "--allowedTools",
        ",".join(allowed_prefixes),
        # Deny-by-default for anything not explicitly allowed above.
        "--permission-mode",
        "default",
    ]
    if request.model:
        cmd += ["--model", request.model]
    instructions = _resolve_instructions(request)
    if instructions:
        cmd += ["--append-system-prompt", instructions]

    # The prompt is delivered on stdin so content beginning with dashes is never
    # parsed as a CLI flag.
    prompt = request.message

    session_id = request.session_id
    process = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(CLAUDE_WORKDIR),
                limit=10 * 1024 * 1024,  # 10 MB — large MCP results
            )
        except FileNotFoundError:
            logger.error("Claude Code CLI binary not found: %s", CLAUDE_COMMAND)
            msg = "\n\nThe AI agent could not be started — the Claude Code CLI is not installed."
            yield _sse({"text": msg})
            yield "data: [DONE]\n\n"
            return
        except OSError as e:
            logger.error("Failed to spawn Claude subprocess: %s", e)
            yield _sse({"text": "\n\nThe AI agent could not be started due to a system error."})
            yield "data: [DONE]\n\n"
            return

        _active_processes[session_id] = process

        # Hand the prompt over on stdin, then close it so the CLI starts work.
        if process.stdin is not None:
            try:
                process.stdin.write(prompt.encode("utf-8"))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()

        error_detail = ""
        had_response = False
        seen_tool_ids: set[str] = set()
        if process.stdout:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # non-JSON diagnostic line — ignore
                if not isinstance(event, dict):
                    continue

                etype = event.get("type", "")

                # Token-level deltas (the live typing effect) arrive wrapped in
                # a `stream_event` carrying a raw Anthropic streaming event.
                if etype == "stream_event":
                    inner = event.get("event", {}) or {}
                    inner_type = inner.get("type", "")
                    if inner_type == "content_block_start":
                        block = inner.get("content_block", {}) or {}
                        if block.get("type") == "tool_use":
                            block_id = block.get("id", "")
                            name = _tool_display_name(block.get("name", ""))
                            if name and block_id not in seen_tool_ids:
                                seen_tool_ids.add(block_id)
                                yield _sse({"type": "tool_call", "name": name})
                    elif inner_type == "content_block_delta":
                        delta = inner.get("delta", {}) or {}
                        dtype = delta.get("type", "")
                        if dtype == "text_delta" and delta.get("text"):
                            yield _sse({"type": "text", "text": delta["text"]})
                        elif dtype == "thinking_delta" and delta.get("thinking"):
                            yield _sse({"type": "thinking", "text": delta["thinking"]})
                    continue

                # Full assistant message — a fallback for surfacing tool calls
                # when the partial-message stream did not name them. Text is left
                # to the deltas above / the final `result` below to avoid dupes.
                if etype == "assistant":
                    content = (event.get("message", {}) or {}).get("content", []) or []
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        block_id = block.get("id", "")
                        name = _tool_display_name(block.get("name", ""))
                        if name and block_id not in seen_tool_ids:
                            seen_tool_ids.add(block_id)
                            yield _sse({"type": "tool_call", "name": name})
                    continue

                # Terminal event — the canonical final answer (or the failure).
                if etype == "result":
                    if event.get("is_error"):
                        error_detail = (
                            event.get("result")
                            or event.get("subtype")
                            or "Claude Code reported an error."
                        )
                    else:
                        text = event.get("result", "")
                        if text:
                            had_response = True
                            yield _sse({"type": "response", "text": text})
                    continue

        await process.wait()

        if process.returncode != 0 or (error_detail and not had_response):
            stderr_text = ""
            if process.stderr:
                stderr = await process.stderr.read()
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
            detail = error_detail or stderr_text
            logger.warning(
                "Claude subprocess failed (session=%s, rc=%s): %s",
                session_id,
                process.returncode,
                detail,
            )
            combined = f"{stderr_text}\n{error_detail}".lower()
            if "rate limit" in combined or "overloaded" in combined:
                msg = (
                    "\n\nThe AI service rate limit has been reached. "
                    "Please wait a moment and try again."
                )
            elif "auth" in combined or "token" in combined or "credit" in combined:
                msg = (
                    "\n\nAuthentication error with the AI service. "
                    "Please check your credentials or contact your administrator."
                )
            else:
                msg = (
                    "\n\nThe AI agent encountered an error while processing "
                    "your request. Please try again and if the issue persists, "
                    "contact your admin."
                )
            if detail:
                yield _sse({"type": "error_detail", "text": detail})
            yield _sse({"text": msg})

        yield "data: [DONE]\n\n"
    finally:
        _active_processes.pop(session_id, None)
        if process is not None and process.returncode is None:
            logger.info(
                "Terminating Claude subprocess (pid=%s, session=%s)",
                process.pid,
                session_id,
            )
            try:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            except ProcessLookupError:
                pass
        # The MCP filter token is registered/cleared by Django (the MCP server's
        # TTL is the safety net), so nothing to clear here.


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/chat", dependencies=[Depends(_require_gateway_secret)])
async def chat(request: ChatRequest) -> StreamingResponse:
    """Stream a Claude Code response as Server-Sent Events."""
    return StreamingResponse(
        _stream_claude(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/abort/{session_id}", dependencies=[Depends(_require_gateway_secret)])
async def abort(session_id: str) -> dict[str, str]:
    """Abort a running Claude subprocess for the given session."""
    process = _active_processes.pop(session_id, None)
    if process is None or process.returncode is not None:
        return {"status": "not_found"}
    logger.info("Aborting Claude subprocess (pid=%s, session=%s)", process.pid, session_id)
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
    except ProcessLookupError:
        pass
    return {"status": "aborted"}


class UpdateAgentsMdRequest(BaseModel):
    content: str


@app.post("/update-agents-md", dependencies=[Depends(_require_gateway_secret)])
async def update_agents_md(request: UpdateAgentsMdRequest) -> dict[str, str]:
    """Store the system prompt; used as the fallback when a request omits one."""
    AGENTS_MD_PATH.write_text(request.content, encoding="utf-8")
    logger.info("Updated CLAUDE.md (%d chars)", len(request.content))
    return {"status": "ok"}


# ── Guided subscription login via `claude setup-token` ──────────────────────
# Mirrors the Codex device-login UX as closely as Claude's auth allows. Claude
# has no poll-based device-code grant, so `setup-token` is driven instead: it
# prints an authorization URL and then waits for the user to paste back the
# short code shown after they approve in a browser. We run it under a PTY (the
# CLI prompts interactively) and harvest the long-lived OAuth token it prints on
# success. Two-step: /start captures the URL; /submit feeds the code and returns
# the token. Django persists the token; nothing is stored on the container.
#
# NOTE: this depends on the `claude setup-token` I/O shape (prints an https URL,
# reads one line of input, prints an `sk-ant-oat…` token). Verify against the
# pinned CLI version — the regexes below are intentionally forgiving.
_setup_logins: dict[str, dict[str, Any]] = {}
_SETUP_URL_RE = re.compile(r"https?://[^\s'\"]+")
_SETUP_TOKEN_RE = re.compile(r"sk-ant-oat[\w\-]+")
# The pinned CLI renders `setup-token` as an Ink TUI that emits more than plain
# CSI colour codes: charset-designation escapes (e.g. ESC ( B), OSC sequences,
# and bare keypad/charset toggles. Stripping only CSI left fragments like "(B"
# in the captured text and could split the `sk-ant-oat…` token across escapes so
# the regex missed it. Strip the full family so the cleaned buffer is plain text.
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI (colours, cursor moves, …)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (terminated by BEL or ST)
    r"|\x1b[()][0-9A-Za-z]"  # charset designation, e.g. ESC ( B
    r"|\x1b[=>NOc]"  # keypad / charset / reset toggles
)


def _spawn_pty(cmd: list[str], env: dict[str, str]) -> tuple[subprocess.Popen[bytes], int]:
    """Spawn a subprocess attached to a PTY; return (process, master_fd).

    A PTY makes the CLI behave as if it were at an interactive terminal, which
    is required for its setup-token prompt. The master fd is set non-blocking so
    the async reader can poll it without stalling the event loop.
    """
    master, slave = pty.openpty()
    # Use a very wide terminal so the CLI never line-wraps its output. The
    # `setup-token` authorization URL is long (~500 chars); at the default
    # 80-column width the CLI inserts newlines mid-URL, and the capture regex
    # (which stops at whitespace) would truncate it before `redirect_uri`,
    # producing an "Invalid OAuth Request / Missing redirect_uri" error.
    winsize = struct.pack("HHHH", 50, 4000, 0, 0)  # rows, cols, xpixel, ypixel
    fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)
    flags = fcntl.fcntl(master, fcntl.F_GETFL)
    fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return proc, master


async def _pty_read_until(
    master: int, proc: subprocess.Popen[bytes], pattern: re.Pattern[str], timeout: float
) -> tuple[str, re.Match[str] | None]:
    """Accumulate PTY output until `pattern` matches, the process exits, or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    buf = ""
    while loop.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += _ANSI_ESCAPE_RE.sub("", chunk.decode("utf-8", "replace"))
            m = pattern.search(buf)
            if m:
                return buf, m
        else:
            if proc.poll() is not None:
                # Process exited — drain anything still buffered, then stop.
                try:
                    chunk = os.read(master, 4096)
                    if chunk:
                        buf += _ANSI_ESCAPE_RE.sub("", chunk.decode("utf-8", "replace"))
                except OSError:
                    pass
                return buf, pattern.search(buf)
            await asyncio.sleep(0.05)
    return buf, pattern.search(buf)


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except ProcessLookupError:
            pass


def _cleanup_setup_login(login_id: str) -> None:
    state = _setup_logins.pop(login_id, None)
    if not state:
        return
    _kill_proc(state["process"])
    try:
        os.close(state["master"])
    except OSError:
        pass


def _login_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = str(CLAUDE_CONFIG_DIR)
    env["HOME"] = str(CLAUDE_CONFIG_DIR.parent)
    # Don't let an existing credential short-circuit a fresh sign-in.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return env


@app.post(
    "/auth/setup-token/start", dependencies=[Depends(_require_gateway_secret)], response_model=None
)
async def auth_setup_token_start() -> dict[str, Any] | Response:
    """Begin a guided sign-in; return the authorization URL to approve."""
    try:
        proc, master = _spawn_pty([CLAUDE_COMMAND, "setup-token"], _login_env())
    except (FileNotFoundError, OSError) as e:
        logger.error("Failed to start Claude setup-token: %s", e)
        return JSONResponse(
            status_code=503, content={"error": "Could not start the login process."}
        )

    buf, match = await _pty_read_until(master, proc, _SETUP_URL_RE, 60.0)
    if match is None:
        _kill_proc(proc)
        try:
            os.close(master)
        except OSError:
            pass
        logger.warning("Claude setup-token produced no URL: %s", buf.strip()[-300:])
        return JSONResponse(
            status_code=502,
            content={"error": "Could not obtain a sign-in URL from Claude."},
        )

    url = match.group(0).rstrip(".,)")
    login_id = str(uuid.uuid4())
    _setup_logins[login_id] = {"process": proc, "master": master, "verification_url": url}
    return {"login_id": login_id, "verification_url": url}


class SetupTokenSubmit(BaseModel):
    code: str


@app.post(
    "/auth/setup-token/submit/{login_id}",
    dependencies=[Depends(_require_gateway_secret)],
    response_model=None,
)
async def auth_setup_token_submit(
    login_id: str, body: SetupTokenSubmit
) -> dict[str, Any] | Response:
    """Feed the pasted authorization code to setup-token; return the OAuth token."""
    state = _setup_logins.get(login_id)
    if state is None:
        return JSONResponse(status_code=404, content={"status": "not_found"})

    proc: subprocess.Popen[bytes] = state["process"]
    master: int = state["master"]
    try:
        os.write(master, (body.code.strip() + "\n").encode("utf-8"))
    except OSError:
        pass

    buf, match = await _pty_read_until(master, proc, _SETUP_TOKEN_RE, 90.0)
    if match is not None:
        token = match.group(0)
        _cleanup_setup_login(login_id)
        logger.info("Claude setup-token sign-in %s complete", login_id)
        return {"status": "complete", "auth_token": token}

    _cleanup_setup_login(login_id)
    tail = buf.strip()[-500:]
    logger.warning("Claude setup-token sign-in %s failed: %s", login_id, tail)
    return {"status": "error", "error": tail or "Sign-in did not return a token."}


@app.post("/auth/setup-token/cancel/{login_id}", dependencies=[Depends(_require_gateway_secret)])
async def auth_setup_token_cancel(login_id: str) -> dict[str, str]:
    """Cancel a pending guided sign-in and terminate its subprocess."""
    if login_id not in _setup_logins:
        return {"status": "not_found"}
    _cleanup_setup_login(login_id)
    return {"status": "cancelled"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
