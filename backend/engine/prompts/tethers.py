"""Prompt for tether (code<->database) graph generation.

Call site: ``engine/engines/tether_engine.py``. The graph schema lives with the
engine (it also drives the validator); the engine passes the schema example and
the allowed-value sets in so this module stays free of engine imports.
"""

from __future__ import annotations

import json
from typing import Any


def build_tether_prompt(
    tether: Any,
    version_id: int,
    *,
    schema_example: dict[str, Any],
    allowed_kinds: set[str],
    allowed_relationships: set[str],
) -> tuple[str, str]:
    """Return (system_prompt, user_message) for the Codex call.

    Keeps the prompt small (codex passes it as argv) and tells the agent to
    explore via MCP tools, then persist via `save_tether_graph` with rich
    per-node and per-edge metadata so the canvas can show meaningful detail.
    """
    code_src = tether.codebase.name
    db_src = tether.database_doc_source.folder_name

    system = (
        "You are a code↔database analyst. Use the MCP tools to explore the "
        "codebase repository and database documentation, identify which code "
        "files / symbols read or write which tables / columns, and persist the "
        "result by calling `save_tether_graph` with RICH metadata.\n\n"
        "Quality bar:\n"
        "  • Every code-file should have ≥1 code-symbol child where relevant.\n"
        "  • Every db-table edge target should also include the specific "
        "    db-column edges when the column is filterable / foreign-keyed.\n"
        "  • Every node should carry a 1-sentence `description`.\n"
        "  • Every db-column must include `data_type`. Mark PK/FK explicitly.\n"
        "  • Every code-symbol should include `signature` and a short `snippet` "
        "    (≤ 25 lines) showing the actual SQL or query call.\n"
        "  • Every edge should include `description` and an `evidence_snippet` "
        "    + `evidence_lang`. Pick `confidence` honestly.\n\n"
        "Precision still beats recall — omit relationships you are not confident "
        "in. Do NOT paste the graph in chat; only the tool call counts."
    )

    sample_node = json.dumps(schema_example["nodes"][1])
    sample_col = json.dumps(schema_example["nodes"][3])
    sample_edge = json.dumps(schema_example["edges"][0])

    user = (
        f"# Task\n"
        f"Build a graph linking codebase '{code_src}' to database '{db_src}', "
        f"then save it by calling "
        f"`save_tether_graph(version_id={version_id}, codebase_summary=..., "
        f"database_summary=..., nodes=[...], edges=[...])`.\n\n"
        f"# How to gather context\n"
        f"- Explore codebase '{code_src}' with `get_codebase_tree(codebase=\"{code_src}\")`, "
        f'`search_codebase(codebase="{code_src}", ...)`, and '
        f'`read_codebase_file(codebase="{code_src}", ...)`.\n'
        f'- `search_docs(source="{db_src}", ...)` for database docs.\n'
        f"- `list_tables` / `get_table_schema` / `query_database` if a live DB is connected.\n"
        f"- `get_query_examples` for known SQL patterns.\n"
        f"Plan multiple search rounds; don't stop at the first hit.\n\n"
        f"# Schema (v2)\n"
        f"- node.kind ∈ {sorted(allowed_kinds)}\n"
        f"- edge.relationship ∈ {sorted(allowed_relationships)}\n"
        f"- code-symbol must have a code-file parent_id; "
        f"db-column must have a db-table parent_id.\n"
        f"- Edge endpoints must be ids that appear in `nodes`.\n"
        f"- confidence ∈ [0.0, 1.0].\n\n"
        f"# Example code-symbol node (with snippet)\n"
        f"{sample_node}\n\n"
        f"# Example db-column node (with type / FK)\n"
        f"{sample_col}\n\n"
        f"# Example edge (with evidence snippet)\n"
        f"{sample_edge}\n\n"
        f"# Output rules\n"
        f"1. Aim for breadth: enumerate every relevant table and at least the key "
        f"columns; enumerate every code file that touches the DB and the specific "
        f"functions inside.\n"
        f"2. Snippets must be the *actual* SQL/code text — quote, don't paraphrase.\n"
        f"3. Each db-column you cite from an edge must exist as a node.\n"
        f"4. When done, call `save_tether_graph` with version_id={version_id}."
    )
    return system, user
