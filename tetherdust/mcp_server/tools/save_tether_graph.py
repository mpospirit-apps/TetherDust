"""Tool: save_tether_graph — persist a generated tether graph to a TetherVersion."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import Field

from ._admin_db import get_admin_engine

logger = logging.getLogger(__name__)


ALLOWED_KINDS = {"code-file", "code-symbol", "db-table", "db-column"}
ALLOWED_RELATIONSHIPS = {"reads", "writes", "references", "maps-to"}
PARENT_KIND = {"code-symbol": "code-file", "db-column": "db-table"}


def _validate_graph(nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> str | None:
    """Return None if valid, else an error string. Mirrors chat.tether_engine.validate."""
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return "`nodes` and `edges` must both be arrays."

    seen_ids: dict[str, str] = {}
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            return f"Node #{i} is not an object."
        nid = node.get("id")
        kind = node.get("kind")
        if not isinstance(nid, str) or not nid:
            return f"Node #{i} missing string `id`."
        if kind not in ALLOWED_KINDS:
            return f"Node {nid!r} has invalid kind {kind!r}."
        if nid in seen_ids:
            return f"Duplicate node id {nid!r}."
        seen_ids[nid] = kind
        if "label" not in node or not isinstance(node["label"], str):
            return f"Node {nid!r} missing string `label`."

    for node in nodes:
        nid = node["id"]
        kind = node["kind"]
        parent_id = node.get("parent_id")
        if parent_id is None:
            if kind in PARENT_KIND:
                return f"Node {nid!r} is a {kind} but has no parent_id."
            continue
        if parent_id not in seen_ids:
            return f"Node {nid!r} references unknown parent_id {parent_id!r}."
        expected = PARENT_KIND.get(kind)  # type: ignore[call-overload]
        if expected and seen_ids[parent_id] != expected:
            return (
                f"Node {nid!r} ({kind}) has parent of wrong kind "
                f"{seen_ids[parent_id]!r}; expected {expected!r}."
            )

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            return f"Edge #{i} is not an object."
        src = edge.get("source_id")
        tgt = edge.get("target_id")
        rel = edge.get("relationship")
        if src not in seen_ids or tgt not in seen_ids:
            return f"Edge #{i} references unknown node ids: {src!r} -> {tgt!r}."
        if rel not in ALLOWED_RELATIONSHIPS:
            return f"Edge #{i} has invalid relationship {rel!r}."
        conf = edge.get("confidence", 1.0)
        if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
            return f"Edge #{i} has invalid confidence {conf!r}; must be in [0.0, 1.0]."
    return None


async def save_tether_graph(
    version_id: Annotated[
        int,
        Field(description="ID of the TetherVersion row to populate. Provided in the user prompt."),
    ],
    nodes: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "Node objects. Required keys: id (str), label (str), "
                "kind ('code-file'|'code-symbol'|'db-table'|'db-column'), "
                "parent_id (str|null). "
                "Recommended optional keys per kind:\n"
                "  - code-file: description, language, path\n"
                "  - code-symbol: description, language, signature, snippet, line_range\n"
                "  - db-table: description, schema, row_count_hint\n"
                "  - db-column: description, data_type, nullable, primary_key, foreign_key\n"
                "code-symbol must have a code-file parent; db-column must have a db-table parent."
            ),
        ),
    ],
    edges: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "Edge objects. Required keys: source_id, target_id, "
                "relationship ('reads'|'writes'|'references'|'maps-to'), "
                "confidence (float in [0.0, 1.0]). "
                "Recommended optional keys: description (one-sentence why), "
                "evidence_snippet (the actual SQL/code excerpt), "
                "evidence_lang ('sql'|'python'|'csharp'|'typescript'|...). "
                "Endpoints must reference ids that appear in `nodes`."
            ),
        ),
    ],
    codebase_summary: Annotated[
        str,
        Field(
            description=(
                "1–3 sentence overview of what the codebase does and how it talks to the DB. "
                "Shown above the canvas in the side panel."
            ),
        ),
    ] = "",
    database_summary: Annotated[
        str,
        Field(
            description=(
                "1–3 sentence overview of the database — main tables, entry points, conventions. "
                "Shown above the canvas in the side panel."
            ),
        ),
    ] = "",
) -> str:
    """Persist a tether graph (nodes + edges + summaries) to a TetherVersion. \
Validates the schema first; on success, marks the version successful and promotes \
it to the tether's current_version. Returns a JSON status string."""
    from sqlalchemy import text

    err = _validate_graph(nodes, edges)
    if err is not None:
        return json.dumps({"success": False, "error": f"Schema validation failed: {err}"})

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return json.dumps({"success": False, "error": str(e)})

    now = datetime.now(UTC)
    graph = {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "codebase_summary": codebase_summary or "",
        "database_summary": database_summary or "",
        "nodes": nodes,
        "edges": edges,
    }

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT tether_id, started_at FROM core_tetherversion WHERE id = :id"),
                {"id": version_id},
            ).fetchone()
            if row is None:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"TetherVersion {version_id} not found.",
                    }
                )
            tether_id = row[0]
            started_at = row[1]

            elapsed_ms = None
            if started_at is not None:
                try:
                    delta = now - started_at
                    elapsed_ms = int(delta.total_seconds() * 1000)
                except Exception:
                    elapsed_ms = None

            conn.execute(
                text(
                    "UPDATE core_tetherversion SET "
                    "graph_json = :graph, status = 'success', completed_at = :now, "
                    "execution_time_ms = COALESCE(:elapsed, execution_time_ms), "
                    "error_message = '' "
                    "WHERE id = :id"
                ),
                {
                    "graph": json.dumps(graph),
                    "now": now,
                    "elapsed": elapsed_ms,
                    "id": version_id,
                },
            )
            conn.execute(
                text(
                    "UPDATE core_tether SET current_version_id = :vid,"  # noqa: E501
                    " updated_at = :now WHERE id = :tid"
                ),
                {"vid": version_id, "now": now, "tid": tether_id},
            )
            conn.commit()

        logger.info(
            "Saved tether graph: version_id=%d, nodes=%d, edges=%d",
            version_id,
            len(nodes),
            len(edges),
        )
        return json.dumps(
            {
                "success": True,
                "version_id": version_id,
                "nodes": len(nodes),
                "edges": len(edges),
            }
        )
    except Exception as e:
        logger.error("Failed to save tether graph for version %d: %s", version_id, e, exc_info=True)
        return json.dumps({"success": False, "error": str(e)})
