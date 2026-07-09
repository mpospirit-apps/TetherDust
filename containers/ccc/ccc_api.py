"""FastAPI wrapper around the ``ccc`` (cocoindex-code) CLI.

An internal, reusable semantic-search service — the same "wrap a CLI behind a
small HTTP API" pattern as the Codex/Claude agent gateways. It owns the embedding
model and the on-disk index; callers (tdmcp for search, the backend/celery for
indexing) talk to it over HTTP with a shared-secret header.

The API is content-agnostic: a *project* is any path under the mounted
``sources/`` tree (``sources/codebases/<name>`` today, ``sources/docs/<folder>``
later), so new domains reuse this service without changes here.

Endpoints:
- ``POST /index  {project}``                          → build/refresh the index
- ``POST /search {project, query, limit, lang, path}`` → semantic search
- ``GET  /healthz``                                    → liveness
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ccc_api")

# All projects live under this mount (``./sources`` bind-mounted at build/run).
APP_ROOT = Path(os.getenv("CCC_APP_ROOT", "/app")).resolve()
SOURCES_ROOT = (APP_ROOT / "sources").resolve()

INDEX_TIMEOUT = int(os.getenv("CCC_INDEX_TIMEOUT", "600"))
SEARCH_TIMEOUT = int(os.getenv("CCC_SEARCH_TIMEOUT", "60"))

app = FastAPI(title="TetherDust ccc gateway")


def require_secret(x_gateway_secret: Annotated[str | None, Header()] = None) -> None:
    """Reject calls without the shared secret (no-op when unset, for local dev)."""
    secret = os.getenv("AGENT_GATEWAY_SECRET", "")
    if secret and x_gateway_secret != secret:
        raise HTTPException(status_code=401, detail="Invalid gateway secret.")


class IndexRequest(BaseModel):
    project: str


class SearchRequest(BaseModel):
    project: str
    query: str
    limit: int = 10
    lang: str | None = None
    path: str | None = None


def _project_dir(project: str) -> Path:
    """Resolve a project path to a directory under ``sources/`` (reject traversal)."""
    target = (APP_ROOT / project).resolve()
    if not (target == SOURCES_ROOT or SOURCES_ROOT in target.parents):
        raise HTTPException(status_code=400, detail="project must be under sources/.")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"project '{project}' not found on disk.")
    return target


def _run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    logger.info("ccc %s (cwd=%s)", " ".join(args[1:]), cwd)
    return subprocess.run(
        args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,  # global settings make init/index non-interactive
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


_RESULT_RE = re.compile(r"^--- Result \d+ \(score: ([0-9.]+)\) ---$", re.MULTILINE)
_FILE_RE = re.compile(r"^File: (?P<path>.+?)(?::(?P<lines>\d+(?:-\d+)?))? \[(?P<lang>[^\]]+)\]$")


def _parse_search(stdout: str) -> list[dict[str, object]]:
    """Parse ``ccc search`` human output into structured hits."""
    results: list[dict[str, object]] = []
    headers = list(_RESULT_RE.finditer(stdout))
    for i, m in enumerate(headers):
        score = float(m.group(1))
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(stdout)
        block_lines = stdout[body_start:body_end].strip("\n").split("\n")
        if not block_lines:
            continue
        file_match = _FILE_RE.match(block_lines[0].strip())
        if file_match:
            path = file_match.group("path")
            lines = file_match.group("lines")
            lang = file_match.group("lang")
            snippet = "\n".join(block_lines[1:]).strip()
        else:
            path, lines, lang, snippet = block_lines[0], None, None, ""
        results.append(
            {"path": path, "lines": lines, "lang": lang, "score": score, "snippet": snippet}
        )
    return results


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/index", dependencies=[Depends(require_secret)])
def index(req: IndexRequest) -> dict[str, object]:
    proj = _project_dir(req.project)
    # Initialize the ccc project once; global settings.yml keeps init non-interactive.
    if not (proj / ".cocoindex_code" / "settings.yml").exists():
        init = _run(["ccc", "init", "-f"], proj, INDEX_TIMEOUT)
        if init.returncode != 0:
            logger.error("ccc init failed: %s", init.stderr)
            raise HTTPException(status_code=500, detail=f"ccc init failed: {init.stderr[-500:]}")
    result = _run(["ccc", "index"], proj, INDEX_TIMEOUT)
    if result.returncode != 0:
        logger.error("ccc index failed: %s", result.stderr)
        raise HTTPException(status_code=500, detail=f"ccc index failed: {result.stderr[-500:]}")
    return {"status": "ok", "project": req.project, "detail": result.stdout[-2000:]}


@app.post("/search", dependencies=[Depends(require_secret)])
def search(req: SearchRequest) -> dict[str, object]:
    proj = _project_dir(req.project)
    if not (proj / ".cocoindex_code" / "settings.yml").exists():
        raise HTTPException(status_code=409, detail="project not indexed yet.")
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required.")
    args = ["ccc", "search", req.query, "--limit", str(max(1, min(req.limit, 50)))]
    if req.lang:
        args += ["--lang", req.lang]
    if req.path:
        args += ["--path", req.path]
    result = _run(args, proj, SEARCH_TIMEOUT)
    if result.returncode != 0:
        logger.error("ccc search failed: %s", result.stderr)
        raise HTTPException(status_code=500, detail=f"ccc search failed: {result.stderr[-500:]}")
    return {"results": _parse_search(result.stdout), "raw": result.stdout}
