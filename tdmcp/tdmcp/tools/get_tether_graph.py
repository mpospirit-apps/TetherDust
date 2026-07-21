"""Tool: get_tether_graph — return the current graph data for a Tether."""

import json
import logging
from typing import Annotated

from pydantic import Field

from ._admin_db import get_admin_engine
from ._db_shared import get_allowed_tethers

logger = logging.getLogger(__name__)


async def get_tether_graph(
    tether_id: Annotated[
        str,
        Field(description="ID of the tether (from list_tethers)."),
    ],
) -> str:
    """Return the current graph for a Tether — the AI-generated map of how \
codebase entities relate to database tables.

Use list_tethers first to find tether IDs. The graph describes nodes \
(code modules, classes, functions, database tables) and edges (the \
relationships between them), giving a structural overview of how the \
codebase and database are coupled."""
    from sqlalchemy import text

    if not tether_id:
        return "Error: tether_id parameter is required"

    allowed = get_allowed_tethers()
    if allowed is not None and tether_id not in allowed:
        return f"Access denied: tether '{tether_id}' is not available for your role."

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT t.name, t.description, "
                    "       cb.name AS codebase_name, "
                    "       ds.name AS database_source_name, "
                    "       tv.version_number, tv.graph_json, tv.completed_at "
                    "FROM engine_tether t "
                    "LEFT JOIN engine_codebase cb ON cb.id = t.codebase_id "
                    "LEFT JOIN engine_documentationsource ds ON ds.id = t.database_doc_source_id "
                    "LEFT JOIN engine_tetherversion tv ON tv.id = t.current_version_id "
                    "WHERE t.id = :tether_id AND t.is_active = true"
                ),
                {"tether_id": tether_id},
            ).fetchone()
    except ValueError:
        return f"Error: tether_id must be a numeric ID, got '{tether_id}'."
    except Exception as e:
        logger.error("Failed to get tether %s: %s", tether_id, e, exc_info=True)
        return f"Error retrieving tether: {e}"

    if row is None:
        return f"Tether with id '{tether_id}' not found or is inactive."

    if not row.graph_json:
        return (
            f"Tether '{row.name}' has no generated graph yet. "
            "Run the tether generation from the admin console first."
        )

    graph = row.graph_json
    if isinstance(graph, str):
        try:
            graph = json.loads(graph)
        except Exception:
            return f"Tether '{row.name}' graph data is malformed."

    # Build a human-readable summary of the graph
    lines = [f"# Tether: {row.name}\n"]
    if row.description:
        lines.append(f"{row.description}\n")

    completed = row.completed_at.strftime("%Y-%m-%d %H:%M UTC") if row.completed_at else "unknown"
    lines.append(f"**Codebase:** {row.codebase_name or 'unknown'}")
    lines.append(f"**Database source:** {row.database_source_name or 'unknown'}")
    lines.append(f"**Version:** v{row.version_number} (generated {completed})\n")

    # Summarise nodes and edges
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if nodes:
        lines.append(f"## Nodes ({len(nodes)} total)\n")
        for node in nodes:
            node_id = node.get("id", "")
            label = node.get("label") or node.get("name") or node_id
            node_type = node.get("type") or node.get("group") or ""
            type_str = f" [{node_type}]" if node_type else ""
            description = node.get("description") or node.get("summary") or ""
            desc_str = f" — {description}" if description else ""
            lines.append(f"- **{label}**{type_str}{desc_str}")
        lines.append("")

    if edges:
        lines.append(f"## Relationships ({len(edges)} total)\n")
        for edge in edges:
            source = edge.get("source") or edge.get("from") or ""
            target = edge.get("target") or edge.get("to") or ""
            label = edge.get("label") or edge.get("type") or "→"
            lines.append(f"- {source} **{label}** {target}")
        lines.append("")

    if not nodes and not edges:
        # Fall back to raw JSON if the structure is non-standard
        lines.append("## Raw graph data\n")
        lines.append(f"```json\n{json.dumps(graph, indent=2)}\n```")

    return "\n".join(lines)
