"""Tether generation engine.

Owns the JSON graph schema, validator, and the synchronous `generate_tether`
entry point that drives the Codex agent and persists results onto a
`TetherVersion`. Called from the Celery task in `core.tasks`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from django.utils import timezone

from ..agents.stream import parse_chunk, scrub_markers, tool_status_label
from ..prompts import build_tether_prompt

if TYPE_CHECKING:
    from ..agents.base import BaseAgent
    from ..models import TetherVersion

# Codex HTTP timeout for tether generation. The default 300s is far too short
# for a rich graph; mirror the chartgen pattern with a 30-minute ceiling.
TETHER_GEN_TIMEOUT_SECONDS = float(os.getenv("TETHER_GEN_TIMEOUT", "1800"))

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------

SCHEMA_VERSION = 2

ALLOWED_KINDS = {"code-file", "code-symbol", "db-table", "db-column"}
ALLOWED_RELATIONSHIPS = {"reads", "writes", "references", "maps-to"}

PARENT_KIND = {
    "code-symbol": "code-file",
    "db-column": "db-table",
}

# Maximum bytes of agent stream kept on a failed run for debugging.
MAX_LOG_EXCERPT_BYTES = 4_000


SCHEMA_EXAMPLE = {
    "schema_version": 2,
    "generated_at": "2026-04-27T12:34:00Z",
    "codebase_source": "my-app-code",
    "database_source": "warehouse-docs",
    "codebase_summary": "Order/checkout service. Repos read & write the warehouse DB; "
    "no ORM — raw SQL via asyncpg.",
    "database_summary": "Single Postgres DB. `orders` is the canonical table; `order_lines` "
    "is its child. `customers` referenced via FK.",
    "nodes": [
        {
            "id": "code:src/orders/repo.py",
            "label": "orders/repo.py",
            "kind": "code-file",
            "parent_id": None,
            "description": "Order persistence layer. All order CRUD lives here.",
            "language": "python",
            "path": "src/orders/repo.py",
        },
        {
            "id": "code:src/orders/repo.py#fetch",
            "label": "fetch_orders()",
            "kind": "code-symbol",
            "parent_id": "code:src/orders/repo.py",
            "description": "Returns all orders for a customer, newest first.",
            "language": "python",
            "signature": "async def fetch_orders(customer_id: int) -> list[Order]",
            "snippet": "async def fetch_orders(customer_id: int) -> list[Order]:\n"
            "    return await db.fetch(\n"
            "        'SELECT id, customer_id, total FROM orders '\n"
            "        'WHERE customer_id = $1 ORDER BY id DESC',\n"
            "        customer_id,\n"
            "    )",
        },
        {
            "id": "db:public.orders",
            "label": "orders",
            "kind": "db-table",
            "parent_id": None,
            "description": "Top-level orders table. ~10M rows. Append-mostly.",
            "schema": "public",
            "row_count_hint": "~10M",
        },
        {
            "id": "db:public.orders.order_id",
            "label": "order_id",
            "kind": "db-column",
            "parent_id": "db:public.orders",
            "description": "Surrogate primary key.",
            "data_type": "BIGINT",
            "nullable": False,
            "primary_key": True,
        },
        {
            "id": "db:public.orders.customer_id",
            "label": "customer_id",
            "kind": "db-column",
            "parent_id": "db:public.orders",
            "description": "FK → customers.id. Indexed.",
            "data_type": "BIGINT",
            "nullable": False,
            "foreign_key": "public.customers.id",
        },
    ],
    "edges": [
        {
            "source_id": "code:src/orders/repo.py#fetch",
            "target_id": "db:public.orders",
            "relationship": "reads",
            "confidence": 0.95,
            "description": "Single SELECT scoped by customer_id; returns all columns.",
            "evidence_snippet": "SELECT id, customer_id, total FROM orders\n"
            "WHERE customer_id = $1 ORDER BY id DESC",
            "evidence_lang": "sql",
        },
        {
            "source_id": "code:src/orders/repo.py#fetch",
            "target_id": "db:public.orders.customer_id",
            "relationship": "references",
            "confidence": 0.95,
            "description": "Read-time filter on customer_id.",
            "evidence_snippet": "WHERE customer_id = $1",
            "evidence_lang": "sql",
        },
    ],
}

# Optional node fields, by kind. The validator allows anything in this set; it
# rejects unknown keys to keep payloads predictable.
OPTIONAL_NODE_FIELDS: dict[str, set[str]] = {
    "code-file": {"description", "language", "path"},
    "code-symbol": {"description", "language", "signature", "snippet", "line_range"},
    "db-table": {"description", "schema", "row_count_hint"},
    "db-column": {"description", "data_type", "nullable", "primary_key", "foreign_key"},
}
REQUIRED_NODE_FIELDS = {"id", "label", "kind", "parent_id"}

OPTIONAL_EDGE_FIELDS = {
    "description",
    "evidence",
    "evidence_snippet",
    "evidence_lang",
}
REQUIRED_EDGE_FIELDS = {"source_id", "target_id", "relationship", "confidence"}


class TetherSchemaError(ValueError):
    """Raised when an agent-generated graph fails validation."""


def validate(graph: dict[str, object]) -> None:
    """Validate a parsed graph dict in place. Raises TetherSchemaError on issues."""
    if not isinstance(graph, dict):
        raise TetherSchemaError("Graph must be a JSON object.")

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TetherSchemaError("`nodes` and `edges` must both be arrays.")

    seen_ids: dict[str, str] = {}  # id -> kind
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise TetherSchemaError(f"Node #{i} is not an object.")
        nid = node.get("id")
        kind = node.get("kind")
        if not isinstance(nid, str) or not nid:
            raise TetherSchemaError(f"Node #{i} missing string `id`.")
        if kind not in ALLOWED_KINDS:
            raise TetherSchemaError(f"Node {nid!r} has invalid kind {kind!r}.")
        assert isinstance(kind, str)
        if nid in seen_ids:
            raise TetherSchemaError(f"Duplicate node id {nid!r}.")
        seen_ids[nid] = kind
        if "label" not in node or not isinstance(node["label"], str):
            raise TetherSchemaError(f"Node {nid!r} missing string `label`.")

    # Parent-id integrity (second pass so order doesn't matter).
    for node in nodes:
        nid = node["id"]
        kind = node["kind"]
        parent_id = node.get("parent_id")
        if parent_id is None:
            if kind in PARENT_KIND:
                raise TetherSchemaError(f"Node {nid!r} is a {kind} but has no parent_id.")
            continue
        if parent_id not in seen_ids:
            raise TetherSchemaError(f"Node {nid!r} references unknown parent_id {parent_id!r}.")
        expected_parent_kind = PARENT_KIND.get(kind)
        if expected_parent_kind and seen_ids[parent_id] != expected_parent_kind:
            raise TetherSchemaError(
                f"Node {nid!r} ({kind}) has parent of wrong kind "
                f"{seen_ids[parent_id]!r}; expected {expected_parent_kind!r}."
            )

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise TetherSchemaError(f"Edge #{i} is not an object.")
        src = edge.get("source_id")
        tgt = edge.get("target_id")
        rel = edge.get("relationship")
        if src not in seen_ids or tgt not in seen_ids:
            raise TetherSchemaError(f"Edge #{i} references unknown node ids: {src!r} -> {tgt!r}.")
        if rel not in ALLOWED_RELATIONSHIPS:
            raise TetherSchemaError(f"Edge #{i} has invalid relationship {rel!r}.")
        conf = edge.get("confidence", 1.0)
        if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
            raise TetherSchemaError(
                f"Edge #{i} has invalid confidence {conf!r}; must be in [0.0, 1.0]."
            )


# -----------------------------------------------------------------------------
# Generation
# -----------------------------------------------------------------------------


async def _collect_codex_response(
    agent: BaseAgent,
    message: str,
    user_id: int,
    on_status: Callable[[str], None] | None,
    allowed_tools: list[str] | None = None,
    allowed_doc_sources: list[str] | None = None,
    timeout: float | None = None,
    allowed_codebases: list[str] | None = None,
) -> str:
    """Drive the streaming agent and join text + RESPONSE chunks.

    `on_status(text)` is a *sync* callback. We wrap each invocation in
    `run_in_executor` so that any DB writes inside it run off-loop —
    Django forbids sync ORM calls from inside an async context.
    """
    parts: list[str] = []
    final_response: str | None = None
    raw_log: list[str] = []
    session_id = f"tether-{uuid.uuid4().hex}"
    loop = asyncio.get_running_loop()

    async for chunk in agent.chat(
        message=message,
        user_id=user_id,
        session_id=session_id,
        allowed_tools=allowed_tools,
        allowed_databases=[],
        allowed_doc_sources=allowed_doc_sources,
        allowed_codebases=allowed_codebases,
        timeout=timeout,
    ):
        raw_log.append(chunk)
        event = parse_chunk(chunk)
        status_text: str | None = None
        if event.kind == "tool":
            status_text = tool_status_label(event.text)
        elif event.kind == "response":
            final_response = event.text
            status_text = event.text.strip()
        elif event.kind == "thinking":
            status_text = event.text.strip()
        else:
            parts.append(event.text)
            status_text = event.text.strip()
        if status_text and on_status:
            await loop.run_in_executor(None, on_status, status_text)

    text = final_response if final_response is not None else "".join(parts)
    agent._tether_raw_log = "".join(raw_log)
    return text


def generate_tether(version: TetherVersion) -> None:
    """Generate the graph for `version`, persisting status + graph_json.

    The agent calls the `save_tether_graph` MCP tool to persist the graph;
    this function streams the agent thoughts into `agent_log_excerpt` so the
    detail page can poll for live status, then re-reads the version row to
    confirm the tool actually ran. Mirrors the docs/dashboard pattern.
    """
    from ..agents import build_agent
    from ..models import AgentConfiguration, ToolConfiguration

    started_wall = time.monotonic()
    tether = version.tether

    try:
        system_prompt, user_message = build_tether_prompt(
            tether,
            version.pk,
            schema_example=SCHEMA_EXAMPLE,
            allowed_kinds=ALLOWED_KINDS,
            allowed_relationships=ALLOWED_RELATIONSHIPS,
        )

        agent_config = AgentConfiguration.get_active()
        if agent_config is None:
            raise RuntimeError("No active AgentConfiguration; cannot generate tether.")
        agent_config_clone = AgentConfiguration(
            name=agent_config.name,
            agent_type=agent_config.agent_type,
            system_prompt=system_prompt,
            service_url=agent_config.service_url,
            settings=agent_config.settings,
        )
        # Carry both credentials so the clone authenticates for either agent type.
        agent_config_clone._auth_token = agent_config._auth_token
        agent_config_clone._api_key = agent_config._api_key
        agent = build_agent(agent_config_clone)

        # Grant the agent every enabled MCP tool plus save_tether_graph.
        enabled_tools = list(
            ToolConfiguration.objects.filter(
                is_enabled=True, mcp_server__is_active=True
            ).values_list("tool_name", flat=True)
        )
        if "save_tether_graph" not in enabled_tools:
            enabled_tools.append("save_tether_graph")
        # Allow the database doc source and the codebase repository so the agent
        # can drill into either side.
        allowed_doc_sources = [tether.database_doc_source.folder_name]
        allowed_codebases = [tether.codebase.name]

        version.prompt_used = user_message
        version.agent_log_excerpt = "Starting agent…"
        version.save(update_fields=["prompt_used", "agent_log_excerpt"])

        from ..models import TetherVersion

        def _push_status(text: str) -> None:
            snippet = scrub_markers((text or "").strip())
            if not snippet:
                return
            snippet = snippet[-MAX_LOG_EXCERPT_BYTES:]
            TetherVersion.objects.filter(pk=version.pk).update(agent_log_excerpt=snippet)

        asyncio.run(
            _collect_codex_response(
                agent,
                user_message,
                version.triggered_by.pk if version.triggered_by else 0,
                _push_status,
                allowed_tools=enabled_tools,
                allowed_doc_sources=allowed_doc_sources,
                allowed_codebases=allowed_codebases,
                timeout=TETHER_GEN_TIMEOUT_SECONDS,
            )
        )

        # The agent's save_tether_graph tool call (if it succeeded) updated the
        # row directly. Re-read to find out whether it did.
        version.refresh_from_db()
        if version.status == "success" and version.graph_json:
            return

        # Tool was not called (or call failed). Surface that as a failure.
        raise RuntimeError(
            "Agent did not call save_tether_graph. Check the agent log for the "
            "model's chat-only response."
        )

    except Exception as exc:
        logger.exception("Tether generation failed for version %s", version.pk)
        excerpt = ""
        try:
            agent_obj = locals().get("agent")
            raw = getattr(agent_obj, "_tether_raw_log", "") if agent_obj else ""
            excerpt = scrub_markers(raw)[-MAX_LOG_EXCERPT_BYTES:]
        except Exception:
            excerpt = ""
        version.status = "failed"
        version.completed_at = timezone.now()
        version.execution_time_ms = int((time.monotonic() - started_wall) * 1000)
        version.error_message = scrub_markers(f"{type(exc).__name__}: {exc}")
        version.agent_log_excerpt = excerpt
        version.save(
            update_fields=[
                "status",
                "completed_at",
                "execution_time_ms",
                "error_message",
                "agent_log_excerpt",
            ]
        )
