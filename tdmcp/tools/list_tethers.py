"""Tool: list_tethers — list accessible codebase × database tether links."""

import logging

from ._admin_db import get_admin_engine
from ._db_shared import get_allowed_tethers

logger = logging.getLogger(__name__)


async def list_tethers() -> str:
    """List all Tethers the current user can access.

A Tether is a visual link between a codebase and a database that maps how \
code entities relate to database tables. Use this tool to discover available \
tethers before calling get_tether_graph. Returns each tether's name, \
description, linked codebase and database, and the status of its latest \
generated version."""
    from sqlalchemy import text

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    allowed = get_allowed_tethers()

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT t.id, t.name, t.description, "
                    "       cb.name AS codebase_name, "
                    "       ds.name AS database_source_name, "
                    "       tv.status AS version_status, "
                    "       tv.version_number, "
                    "       tv.completed_at "
                    "FROM core_tether t "
                    "LEFT JOIN core_codebase cb ON cb.id = t.codebase_id "
                    "LEFT JOIN core_documentationsource ds ON ds.id = t.database_doc_source_id "
                    "LEFT JOIN core_tetherversion tv ON tv.id = t.current_version_id "
                    "WHERE t.is_active = true "
                    "ORDER BY t.name"
                )
            ).fetchall()
    except Exception as e:
        logger.error("Failed to list tethers: %s", e, exc_info=True)
        return f"Error listing tethers: {e}"

    if not rows:
        return "No active tethers found."

    lines = ["# Available Tethers\n"]
    found = 0
    for row in rows:
        tether_id = str(row.id)
        if allowed is not None and tether_id not in allowed:
            continue
        found += 1
        lines.append(f"## {row.name} (id: {tether_id})")
        if row.description:
            lines.append(row.description)
        lines.append(f"- **Codebase:** {row.codebase_name or 'unknown'}")
        lines.append(f"- **Database source:** {row.database_source_name or 'unknown'}")
        if row.version_status:
            completed = row.completed_at.strftime("%Y-%m-%d %H:%M UTC") if row.completed_at else "—"
            lines.append(
                f"- **Current version:** v{row.version_number} "
                f"({row.version_status}, generated {completed})"
            )
        else:
            lines.append("- **Current version:** Not yet generated")
        lines.append("")

    if found == 0:
        return "No tethers are available for your role."

    return "\n".join(lines)
