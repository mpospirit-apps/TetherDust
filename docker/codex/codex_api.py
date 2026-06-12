"""Thin FastAPI wrapper around the Codex CLI subprocess.

Exposes:
  POST /chat   — stream Codex response as SSE
  GET  /healthz — liveness probe

Per-request tool filtering is enforced via a token embedded in the MCP URL
path. Django registers the filter token with the MCP server and hands this
service a ready-tokenized `mcp_url` in the request; this service points the
spawned Codex process at it — inlined as a `codex exec -c` override when no
custom MCP servers are involved, or written into a per-request config.toml when
they are. The MCP server extracts the token, looks up allowed tools, and hides
disallowed tools from list_tools() / blocks them in call_tool(). Django clears
the token when the stream completes; the MCP server's TTL is the safety net.
"""

import asyncio
import base64
import datetime
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Shared secret authenticating Django → gateway calls. The gateway sits on the
# internal Docker network with no user-facing auth; when this is set, every
# endpoint except /healthz requires a matching X-Gateway-Secret header, so a
# process that can reach the gateway can't drive the agent with attacker-chosen
# credentials/permissions or read the stored OAuth credential. Unset disables
# enforcement (a startup warning is logged) for local/dev use.
GATEWAY_SECRET = os.getenv("AGENT_GATEWAY_SECRET", "")

if not GATEWAY_SECRET:
    logger.warning(
        "AGENT_GATEWAY_SECRET is not set — the Codex gateway is UNAUTHENTICATED. "
        "Set it (and the matching value on the web/celery services) before any "
        "non-development use."
    )


def _require_gateway_secret(x_gateway_secret: str | None = Header(default=None)) -> None:
    """FastAPI dependency: reject requests missing the shared secret (when set)."""
    if GATEWAY_SECRET and x_gateway_secret != GATEWAY_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="TetherDust Codex API")

# Track active Codex subprocesses by session_id for explicit abort
_active_processes: dict[str, asyncio.subprocess.Process] = {}

CODEX_COMMAND = os.getenv("CODEX_COMMAND", "codex")
# Sandbox mode for the `codex exec` subprocess that answers chat requests.
# Default "read-only": the model's shell commands cannot write files or open
# network connections, so a prompt-injected or malicious request can't use the
# shell to exfiltrate the container's credential or reach internal hosts (e.g.
# the MCP server's bare endpoint). MCP tool calls are made by Codex core, not by
# the sandboxed shell, so database/doc access is unaffected. Set to
# "danger-full-access" only as an escape hatch where the host kernel can't
# enforce the sandbox (Landlock/seccomp unavailable). Residual: a read-only
# sandbox still lets the model READ and echo files into its reply, so the role
# filter (enforced MCP-side) remains the authoritative access boundary.
CODEX_SANDBOX_MODE = os.getenv("CODEX_SANDBOX_MODE", "read-only")
# Default MCP URL for unrestricted requests (no filter token). Restricted
# requests receive a pre-tokenized `mcp_url` from Django instead.
MCP_URL = os.getenv("MCP_URL", "http://mcp:8001/mcp")
# Directory for per-request Codex homes — must NOT be under /tmp because
# Codex CLI refuses to create helper binaries under temporary directories,
# which breaks MCP tool discovery.
CODEX_HOMES_DIR = Path(os.getenv("CODEX_HOMES_DIR", "/opt/codex-homes"))
CODEX_HOMES_DIR.mkdir(parents=True, exist_ok=True)
# Persistent credential home (backed by the codex-home volume). Holds the
# default config.toml and the "live working copy" of auth.json that Codex
# refreshes in place. Per-request homes are seeded from / harvested back to it.
CODEX_HOME_DIR = Path(os.getenv("CODEX_HOME_DIR", "/var/codex-home/.codex"))
CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)

# Serializes writes to the volume auth.json (seed + harvest). All requests run
# in one event loop, so an asyncio lock is enough for cross-request safety.
_auth_lock = asyncio.Lock()


async def _seed_volume_auth(auth_token: str) -> None:
    """Seed the volume auth.json from the DB secret on cold start (only if missing).

    The volume copy is the live credential Codex refreshes in place; once it
    exists we never overwrite it from the DB token, which may be *older* than a
    refreshed volume copy. Flow C (Celery) keeps the DB in sync the other way.
    """
    auth_path = CODEX_HOME_DIR / "auth.json"
    if auth_path.exists():
        return
    async with _auth_lock:
        if auth_path.exists():
            return
        CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(auth_token)
        logger.info("Seeded volume auth.json from request credential (cold start)")


async def _harvest_volume_auth(per_request_codex_dir: Path) -> None:
    """Copy a refreshed auth.json from a per-request home back to the volume.

    Codex rotates the session token in whichever home it runs from. For
    per-request homes that refresh would be discarded on cleanup, so copy it
    back to the persistent volume whenever it differs from the current copy.
    """
    src = per_request_codex_dir / "auth.json"
    if not src.exists():
        return
    dst = CODEX_HOME_DIR / "auth.json"
    try:
        new_bytes = src.read_bytes()
        if dst.exists() and dst.read_bytes() == new_bytes:
            return
        async with _auth_lock:
            CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(new_bytes)
        logger.info("Harvested refreshed auth.json back to volume")
    except OSError:
        logger.warning("Failed to harvest refreshed auth.json", exc_info=True)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: int
    allowed_tools: Optional[List[str]] = None
    allowed_databases: Optional[List[str]] = None
    allowed_doc_sources: Optional[List[str]] = None
    max_row_limit: Optional[str] = None
    auth_token: Optional[str] = None
    # Provider API key for API-key auth (mutually exclusive with auth_token).
    # Injected as an env var for the subprocess; no auth.json is seeded.
    api_key: Optional[str] = None
    instructions: Optional[str] = None
    # Optional model + reasoning effort overrides for `codex exec`. Both are
    # passed as `-c` config overrides. When absent, Codex uses its built-in
    # defaults. `reasoning_effort` accepts Codex's values
    # (none|minimal|low|medium|high|xhigh); validation is enforced upstream.
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    # Pre-tokenized MCP URL for the built-in tetherdust server, registered by
    # Django for restricted requests. Absent/None means unrestricted (the
    # default MCP_URL is used).
    mcp_url: Optional[str] = None
    # Extra MCP servers the caller's role allows, injected into the per-request
    # config.toml alongside the built-in tetherdust block. Each entry has keys
    # `name`, `url`, `transport`, `auth_token`, `headers`.
    custom_mcp_servers: Optional[List[Dict[str, Any]]] = None


_RESERVED_MCP_KEYS = {"tetherdust"}


def _sanitize_mcp_key(name: str) -> str:
    """Derive a TOML-safe MCP server key from a human-friendly name.

    Codex expects `[mcp_servers.<key>]` keys to be bare identifiers. We
    lowercase, replace non-alphanumerics with `_`, and reserve `tetherdust`
    for the built-in server.
    """
    key = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
    if not key:
        key = "server"
    if key in _RESERVED_MCP_KEYS:
        key = f"{key}_custom"
    return key


def _toml_escape(value: str) -> str:
    """Escape a string for a TOML double-quoted literal."""
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _render_custom_mcp_blocks(servers: List[Dict[str, Any]]) -> str:
    """Render `[mcp_servers.<key>]` blocks for custom servers.

    Collisions on the sanitized key are resolved by suffixing `_2`, `_3`, …
    Servers without a `url` are skipped.
    """
    used: set[str] = set(_RESERVED_MCP_KEYS)
    blocks: list[str] = []
    for server in servers:
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

        headers: Dict[str, str] = dict(server.get("headers") or {})
        auth_token = (server.get("auth_token") or "").strip()
        if auth_token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {auth_token}"

        lines = [f"[mcp_servers.{key}]", f'url = "{_toml_escape(url)}"']
        if headers:
            lines.append("")
            lines.append(f"[mcp_servers.{key}.http_headers]")
            for header_name, header_value in headers.items():
                lines.append(
                    f'"{_toml_escape(str(header_name))}" = "{_toml_escape(str(header_value))}"'
                )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _redact_servers_for_log(servers: Optional[List[Dict[str, Any]]]) -> list:
    """Strip secrets before logging."""
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


def _mcp_url_override_args(mcp_url: str) -> List[str]:
    """Build `codex exec -c` args that inline the built-in tetherdust MCP URL.

    Lets a restricted request with no custom MCP servers run from the persistent
    CODEX_HOME instead of minting a per-request temp home just to write a one-line
    config.toml. The dotted path overrides `url` under `[mcp_servers.tetherdust]`;
    the value is a quoted TOML string (codex parses the value portion as TOML).
    """
    return ["-c", f'mcp_servers.tetherdust.url="{_toml_escape(mcp_url)}"']


def _setup_per_request_home(
    mcp_url: str | None,
    custom_mcp_servers: List[Dict[str, Any]],
    api_key: str | None = None,
) -> str:
    """Create a temp HOME with an isolated .codex/config.toml for this request.

    Used when the request carries custom MCP servers (their nested
    `[mcp_servers.<key>.http_headers]` tables don't map cleanly to `-c`
    overrides) or an API key (Codex's `exec` only reads a credential from
    `auth.json`, never from an env var — see `auth.json` seeding below).
    Restricted requests with neither inline the MCP URL via `codex exec -c`
    instead (see `_mcp_url_override_args`).

    The built-in tetherdust block uses the tokenized `mcp_url` when Django
    supplied one (so the MCP server can enforce the pre-registered tool filter),
    or the plain default URL otherwise (unrestricted role). Custom MCP servers
    are rendered as additional `[mcp_servers.<key>]` blocks.

    Returns the temp dir path; the caller must clean it up.
    """
    tmpdir = tempfile.mkdtemp(prefix="codex_req_", dir=str(CODEX_HOMES_DIR))
    codex_dir = Path(tmpdir) / ".codex"
    codex_dir.mkdir()

    if api_key:
        # API-key auth: Codex 0.114's `exec` ignores OPENAI_API_KEY in the env
        # and authenticates only from auth.json. Write the apikey credential
        # here (isolated per request, never harvested back to the volume). The
        # subscription auth.json is intentionally not copied — this request
        # authenticates by key, not by the shared subscription token.
        (codex_dir / "auth.json").write_text(
            json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": api_key})
        )
    else:
        # Seed the per-request auth.json from the persistent volume copy (never
        # from /root). A refreshed token is harvested back after the request.
        auth_src = CODEX_HOME_DIR / "auth.json"
        if auth_src.exists():
            shutil.copy2(auth_src, codex_dir / "auth.json")

    builtin_url = mcp_url if mcp_url else MCP_URL
    sections = [f'[mcp_servers.tetherdust]\nurl = "{_toml_escape(builtin_url)}"']
    custom_blocks = _render_custom_mcp_blocks(custom_mcp_servers)
    if custom_blocks:
        sections.append(custom_blocks)
    (codex_dir / "config.toml").write_text("\n\n".join(sections) + "\n")

    return tmpdir


async def _stream_codex(request: ChatRequest) -> AsyncIterator[str]:
    """Spawn a Codex CLI subprocess and yield SSE-formatted chunks."""
    env = os.environ.copy()

    if request.allowed_databases is not None:
        env["TETHERDUST_ALLOWED_DATABASES"] = ",".join(request.allowed_databases)
    if request.allowed_doc_sources is not None:
        env["TETHERDUST_ALLOWED_DOC_SOURCES"] = ",".join(request.allowed_doc_sources)
    if request.max_row_limit:
        env["TETHERDUST_MAX_ROW_LIMIT"] = request.max_row_limit

    # Authentication: either an API key or a ChatGPT-subscription auth.json.
    # API key takes precedence and is written into a per-request auth.json below
    # (Codex's `exec` only reads credentials from auth.json), skipping the volume
    # subscription credential entirely. A subscription auth_token seeds the
    # volume on cold start.
    if not request.api_key and request.auth_token:
        # Seed the persistent volume credential from the DB secret on cold start.
        # Only writes if the volume has no auth.json yet, so refreshed tokens are
        # never clobbered. Never touches /root.
        await _seed_volume_auth(request.auth_token)

    logger.debug(
        "Received request: allowed_tools=%s, allowed_databases=%s, "
        "allowed_doc_sources=%s, max_row_limit=%s, model=%s, reasoning_effort=%s, "
        "mcp_url=%s, custom_mcp_servers=%s",
        request.allowed_tools, request.allowed_databases,
        request.allowed_doc_sources, request.max_row_limit,
        request.model, request.reasoning_effort,
        "<tokenized>" if request.mcp_url else None,
        _redact_servers_for_log(request.custom_mcp_servers),
    )

    # Decide how to supply the MCP config to the Codex subprocess:
    #   • Custom MCP servers → a per-request temp home with a full config.toml
    #     (nested `[mcp_servers.<key>.http_headers]` tables don't map cleanly to
    #     `-c` overrides).
    #   • Restricted request, no custom servers → inline the pre-tokenized
    #     `mcp_url` via `codex exec -c` and run from the persistent CODEX_HOME.
    #     This avoids the mkdtemp + config.toml write + rmtree + auth seed/harvest
    #     round-trip on the hot path (#4), and lets refreshed tokens land directly
    #     in the volume.
    #   • Unrestricted, no custom servers → default config.toml already on the
    #     volume; run from CODEX_HOME with no overrides.
    # Django enforces the per-request tool filter from the token in the mcp_url
    # path regardless of which path is taken here.
    config_overrides: List[str] = []
    # Model + reasoning effort overrides apply on every path (per-request home or
    # inline MCP override). Codex parses each `-c` value portion as TOML, so
    # string values are quoted.
    if request.model:
        config_overrides += ["-c", f'model="{_toml_escape(request.model)}"']
    if request.reasoning_effort:
        config_overrides += [
            "-c", f'model_reasoning_effort="{_toml_escape(request.reasoning_effort)}"'
        ]
    # API-key auth also needs a per-request home: the apikey auth.json must be
    # isolated to this request rather than written to the shared volume.
    if request.custom_mcp_servers or request.api_key:
        tmpdir = _setup_per_request_home(
            request.mcp_url, request.custom_mcp_servers or [], api_key=request.api_key
        )
    else:
        tmpdir = None
        if request.mcp_url:
            config_overrides += _mcp_url_override_args(request.mcp_url)
    # Point CODEX_HOME at the config dir (not HOME — smaller blast radius). A
    # per-request home gets its isolated, tokenized config; everything else runs
    # directly from the persistent volume so token refreshes land in place with
    # no harvest needed.
    if tmpdir:
        env["CODEX_HOME"] = str(Path(tmpdir) / ".codex")
    else:
        env["CODEX_HOME"] = str(CODEX_HOME_DIR)

    # Build command args. The agent runs sandboxed (see CODEX_SANDBOX_MODE):
    # commands the model executes are confined, while MCP tool calls — made by
    # Codex core, not the sandboxed shell — keep working. `codex exec` is already
    # non-interactive (it never prompts for approval), so a command the sandbox
    # denies simply fails rather than blocking — no approval flag is needed or
    # accepted (`exec` only takes `--sandbox <mode>`).
    cmd = [
        CODEX_COMMAND,
        "exec",
        "--skip-git-repo-check",
    ]
    if CODEX_SANDBOX_MODE == "danger-full-access":
        # Explicit opt-out — only for hosts where the sandbox can't be enforced.
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd += ["--sandbox", CODEX_SANDBOX_MODE]
    cmd += [
        "--ephemeral",
        "--json",  # emit structured JSONL events so we can surface tool calls
    ]
    # Inline MCP config overrides (restricted, no-custom-server fast path). Must
    # precede the `--` prompt separator so they're parsed as options.
    cmd.extend(config_overrides)

    # Prepend instructions to the prompt (codex exec only takes a single PROMPT)
    prompt = request.message
    if request.instructions and request.instructions.strip():
        prompt = f"{request.instructions.strip()}\n\n{prompt}"

    # "--" signals end of CLI options so the prompt isn't parsed as flags
    # (doc content may start with dashes that confuse the argument parser)
    cmd.append("--")
    cmd.append(prompt)

    session_id = request.session_id
    process = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=10 * 1024 * 1024,  # 10 MB — Notion responses can exceed default 64 KB
            )
        except FileNotFoundError:
            logger.error("Codex CLI binary not found: %s", CODEX_COMMAND)
            error_payload = json.dumps({
                "text": "\n\nThe AI agent could not be started — the Codex CLI is not installed."
            })
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"
            return
        except OSError as e:
            logger.error("Failed to spawn Codex subprocess: %s", e)
            error_payload = json.dumps({
                "text": "\n\nThe AI agent could not be started due to a system error."
            })
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"
            return

        _active_processes[session_id] = process

        # The real failure cause may arrive as a Codex `error` event on stdout
        # (e.g. "model not supported with a ChatGPT account") rather than on
        # stderr. Captured here so it can be surfaced for session-log logging.
        error_detail = ""
        if process.stdout:
            current_item_type = ""
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
                    # Not valid JSON — pass through as raw text
                    payload = json.dumps({"type": "text", "text": line})
                    yield f"data: {payload}\n\n"
                    continue

                event_type = event.get("type", "")
                item = event.get("item", {})
                item_type = item.get("type", "")

                # Capture a structured error event (the genuine failure cause)
                # so it can be logged to the session even though it is not shown
                # to the user as the reply text.
                if event_type == "error":
                    error_detail = event.get("message", "") or error_detail
                    continue

                # Track which item type is currently being streamed so that
                # reasoning/thinking deltas can be distinguished from answer deltas.
                if event_type == "item.created":
                    current_item_type = item_type

                # Tool call started — surface the name immediately
                if event_type == "item.created" and item_type in ("tool_call", "function_call"):
                    name = item.get("name", "")
                    if name:
                        payload = json.dumps({"type": "tool_call", "name": name})
                        yield f"data: {payload}\n\n"

                # Streaming text delta (if Codex emits them).
                # Reasoning/thinking deltas are emitted as "thinking" so the
                # consumer can display them in the status bar without including
                # them in the saved response text.
                elif event_type in ("item.delta", "output_text.delta"):
                    delta = event.get("delta", {})
                    text = delta.get("text", "") if isinstance(delta, dict) else ""
                    if text:
                        is_reasoning = current_item_type in ("reasoning", "thinking")
                        chunk_type = "thinking" if is_reasoning else "text"
                        payload = json.dumps({"type": chunk_type, "text": text})
                        yield f"data: {payload}\n\n"

                # Completed agent message — emit as "response" (distinct from
                # streaming deltas) so the consumer knows this is the final text.
                # Reasoning items are excluded: their content is surfaced via
                # "thinking" deltas above and must not overwrite the real answer.
                elif event_type == "item.completed" and item_type not in (
                    "tool_call", "function_call", "function_call_output",
                    "tool_call_output", "tool_result",
                    "reasoning", "thinking",
                ):
                    text = item.get("text", "") or item.get("content", "")
                    if text:
                        payload = json.dumps({"type": "response", "text": text})
                        yield f"data: {payload}\n\n"

        await process.wait()

        if process.returncode != 0:
            stderr_text = ""
            if process.stderr:
                stderr = await process.stderr.read()
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
            # Prefer the structured stdout `error` event for the real cause;
            # fall back to whatever landed on stderr.
            detail = error_detail or stderr_text
            logger.warning(
                "Codex subprocess failed (session=%s, rc=%s): %s",
                session_id, process.returncode, detail,
            )
            combined = f"{stderr_text}\n{error_detail}".lower()
            if "rate limit" in combined:
                msg = (
                    "\n\nThe AI service rate limit has been reached. "
                    "Please wait a moment and try again."
                )
            elif "auth" in combined or "token" in combined:
                msg = (
                    "\n\nAuthentication error with the AI service. "
                    "Please check your credentials or contact your administrator."
                )
            else:
                msg = (
                    "\n\nThe AI agent encountered an error while processing "
                    "your request. Please try again and if the issue persist, "
                    "contact to your admin."
                )
            # Surface the real cause to Django for session-log persistence. This
            # is logged, not shown to the user as the reply (the friendly `msg`
            # below is the visible text).
            if detail:
                yield f"data: {json.dumps({'type': 'error_detail', 'text': detail})}\n\n"
            yield f"data: {json.dumps({'text': msg})}\n\n"

        yield "data: [DONE]\n\n"
    finally:
        _active_processes.pop(session_id, None)
        # Kill the Codex subprocess if still running (e.g. client disconnected)
        if process is not None and process.returncode is None:
            logger.info(
                "Terminating Codex subprocess (pid=%s, session=%s)",
                process.pid, session_id,
            )
            try:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            except ProcessLookupError:
                pass
        if tmpdir:
            # Capture any token Codex refreshed during this request before the
            # per-request home is deleted, then clean up. API-key homes carry a
            # static apikey credential (no refresh) and must never leak the key
            # back onto the shared volume, so harvesting is skipped for them.
            if not request.api_key:
                await _harvest_volume_auth(Path(tmpdir) / ".codex")
            shutil.rmtree(tmpdir, ignore_errors=True)
        # The MCP filter token is registered and cleared by Django (the TTL on
        # the MCP server is the safety net), so nothing to clear here.


@app.post("/chat", dependencies=[Depends(_require_gateway_secret)])
async def chat(request: ChatRequest):
    """Stream a Codex response as Server-Sent Events."""
    return StreamingResponse(
        _stream_codex(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/abort/{session_id}", dependencies=[Depends(_require_gateway_secret)])
async def abort(session_id: str):
    """Abort a running Codex subprocess for the given session."""
    process = _active_processes.pop(session_id, None)
    if process is None or process.returncode is not None:
        return {"status": "not_found"}

    logger.info("Aborting Codex subprocess (pid=%s, session=%s)", process.pid, session_id)
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    except ProcessLookupError:
        pass
    return {"status": "aborted"}


class UpdateAgentsMdRequest(BaseModel):
    content: str


@app.post("/update-agents-md", dependencies=[Depends(_require_gateway_secret)])
async def update_agents_md(request: UpdateAgentsMdRequest):
    """Update the AGENTS.md file that the Codex CLI reads on each invocation."""
    agents_path = Path("/app/AGENTS.md")
    agents_path.write_text(request.content, encoding="utf-8")
    logger.info("Updated AGENTS.md (%d chars)", len(request.content))
    return {"status": "ok"}


# ── Device-code login (Flow A) ──────────────────────────────────────────────
# In-flight device logins keyed by a generated login_id. Each value holds:
#   {status: "pending"|"complete"|"error", verification_url, user_code,
#    auth_token?, error?, process}
_device_logins: dict[str, dict] = {}

_DEVICE_URL_RE = re.compile(r"https?://[^\s'\"]+")
_DEVICE_CODE_RE = re.compile(r"\b[A-Z0-9]{4,}-[A-Z0-9]{4,}\b")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _parse_token_expiry(auth_json: str) -> str | None:
    """Best-effort extraction of the credential expiry as an ISO timestamp.

    The OpenAI auth.json stores a JWT access token whose payload carries an
    `exp` claim. We decode it without verification (we only need the expiry).
    Returns None on any unexpected shape — callers treat that as "unknown".
    """
    try:
        data = json.loads(auth_json)
    except (json.JSONDecodeError, TypeError):
        return None
    tokens = data.get("tokens") if isinstance(data, dict) else None
    access = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access or access.count(".") != 2:
        return None
    payload_seg = access.split(".")[1]
    payload_seg += "=" * (-len(payload_seg) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload_seg))
    except Exception:
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if not isinstance(exp, (int, float)):
        return None
    return datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat()


async def _capture_device_prompt(
    process: asyncio.subprocess.Process, timeout: float = 60.0
) -> tuple[str | None, str | None]:
    """Read early subprocess output to extract the verification URL + user code."""
    url: str | None = None
    code: str | None = None
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    assert process.stdout is not None
    while url is None or code is None:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if not line_bytes:
            break
        line = _ANSI_ESCAPE_RE.sub("", line_bytes.decode("utf-8", errors="replace"))
        if url is None:
            m = _DEVICE_URL_RE.search(line)
            if m:
                url = m.group(0).rstrip(".,)")
        if code is None:
            m = _DEVICE_CODE_RE.search(line)
            if m:
                code = m.group(0)
    return url, code


async def _await_device_login(login_id: str, process: asyncio.subprocess.Process) -> None:
    """Background task: wait for the login subprocess to finish and record result."""
    try:
        stdout, _ = await process.communicate()
    except Exception:
        logger.exception("Device login %s failed while awaiting completion", login_id)
        state = _device_logins.get(login_id)
        if state is not None:
            state["status"] = "error"
            state["error"] = "Login process failed unexpectedly."
        return
    state = _device_logins.get(login_id)
    if state is None:
        return
    tail = (stdout or b"").decode("utf-8", errors="replace").strip()
    auth_path = CODEX_HOME_DIR / "auth.json"
    if process.returncode == 0 and auth_path.exists():
        try:
            state["auth_token"] = auth_path.read_text()
            state["status"] = "complete"
            logger.info("Device login %s complete", login_id)
        except OSError:
            state["status"] = "error"
            state["error"] = "Signed in but could not read the credential."
    else:
        state["status"] = "error"
        state["error"] = tail[-500:] or f"Login exited with code {process.returncode}."
        logger.warning("Device login %s failed: %s", login_id, state["error"])


@app.post("/auth/device/start", dependencies=[Depends(_require_gateway_secret)])
async def auth_device_start():
    """Begin an in-app device-code login; return the verification URL + code.

    Runs `codex login --device-auth` against the persistent volume HOME so the
    resulting auth.json lands where every request reads it. The process keeps
    polling in the background until the user approves in a browser.
    """
    env = os.environ.copy()
    CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
    env["CODEX_HOME"] = str(CODEX_HOME_DIR)
    try:
        process = await asyncio.create_subprocess_exec(
            CODEX_COMMAND, "login", "--device-auth",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except (FileNotFoundError, OSError) as e:
        logger.error("Failed to start device login: %s", e)
        return JSONResponse(status_code=503, content={"error": "Could not start the login process."})

    url, code = await _capture_device_prompt(process)
    if url is None or code is None:
        if process.returncode is None:
            process.kill()
            await process.wait()
        return JSONResponse(
            status_code=502,
            content={"error": "Could not obtain a device-login code from Codex."},
        )

    login_id = str(uuid.uuid4())
    _device_logins[login_id] = {
        "status": "pending",
        "verification_url": url,
        "user_code": code,
        "process": process,
    }
    asyncio.create_task(_await_device_login(login_id, process))
    return {"login_id": login_id, "verification_url": url, "user_code": code}


@app.get("/auth/device/status/{login_id}", dependencies=[Depends(_require_gateway_secret)])
async def auth_device_status(login_id: str):
    """Poll a device login. On a terminal state the entry is consumed."""
    state = _device_logins.get(login_id)
    if state is None:
        return JSONResponse(status_code=404, content={"status": "not_found"})
    status = state["status"]
    resp: dict[str, Any] = {
        "status": status,
        "verification_url": state.get("verification_url"),
        "user_code": state.get("user_code"),
    }
    if status == "complete":
        resp["auth_token"] = state.get("auth_token", "")
        _device_logins.pop(login_id, None)
    elif status == "error":
        resp["error"] = state.get("error", "")
        _device_logins.pop(login_id, None)
    return resp


@app.post("/auth/device/cancel/{login_id}", dependencies=[Depends(_require_gateway_secret)])
async def auth_device_cancel(login_id: str):
    """Cancel a pending device login and terminate its subprocess."""
    state = _device_logins.pop(login_id, None)
    if state is None:
        return {"status": "not_found"}
    process = state.get("process")
    if process is not None and process.returncode is None:
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
    return {"status": "cancelled"}


@app.get("/auth/token", dependencies=[Depends(_require_gateway_secret)])
async def auth_token():
    """Return the current volume credential (the live, possibly-refreshed token).

    Used by the Django Celery sync task to keep the encrypted DB backup current.
    """
    auth_path = CODEX_HOME_DIR / "auth.json"
    if not auth_path.exists():
        return {"present": False}
    try:
        content = auth_path.read_text()
    except OSError:
        return {"present": False}
    return {
        "present": True,
        "auth_token": content,
        "expires_at": _parse_token_expiry(content),
    }


@app.get("/healthz")
async def healthz():
    """Liveness probe."""
    return {"status": "ok"}
