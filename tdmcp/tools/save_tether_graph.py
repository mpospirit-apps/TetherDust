"""Tool: save_tether_graph — persist a generated tether graph to a TetherVersion."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ._internal_api import call_internal


async def save_tether_graph(
    version_id: Annotated[
        str,
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
    # Schema validation, version update and current_version promotion happen
    # server-side in the internal API; this tool just forwards the graph.
    return await call_internal(
        "POST",
        f"/tether-versions/{version_id}/graph/",
        {
            "nodes": nodes,
            "edges": edges,
            "codebase_summary": codebase_summary,
            "database_summary": database_summary,
        },
    )
