"""Tool: list_reports — list accessible report definitions."""

import logging

from ._admin_db import get_admin_engine
from ._db_shared import get_allowed_reports

logger = logging.getLogger(__name__)


async def list_reports() -> str:
    """List all report definitions the current user can access.

Use this tool to discover available reports before calling get_report_data. \
Returns each report's name, description, associated database, schedule, and \
the status and row count of the most recent execution."""
    from sqlalchemy import text

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    allowed = get_allowed_reports()

    try:
        with engine.connect() as conn:
            query = text(
                "SELECT rd.name, rd.description, rd.schedule_type, rd.is_active, "
                "       dc.name AS database_name, "
                "       re.status AS last_status, re.row_count AS last_row_count, "
                "       re.started_at AS last_run "
                "FROM core_reportdefinition rd "
                "LEFT JOIN core_databaseconnection dc ON dc.id = rd.database_id "
                "LEFT JOIN LATERAL ( "
                "    SELECT status, row_count, started_at "
                "    FROM core_reportexecution "
                "    WHERE definition_id = rd.id "
                "    ORDER BY started_at DESC LIMIT 1 "
                ") re ON true "
                "WHERE rd.is_active = true "
                "ORDER BY rd.name"
            )
            rows = conn.execute(query).fetchall()
    except Exception as e:
        logger.error("Failed to list reports: %s", e, exc_info=True)
        return f"Error listing reports: {e}"

    if not rows:
        return "No active reports found."

    lines = ["# Available Reports\n"]
    found = 0
    for row in rows:
        name = row.name
        if allowed is not None and name not in allowed:
            continue
        found += 1
        lines.append(f"## {name}")
        if row.description:
            lines.append(row.description)
        lines.append(f"- **Database:** {row.database_name or 'unknown'}")
        lines.append(f"- **Schedule:** {row.schedule_type}")
        if row.last_status:
            last_run = row.last_run.strftime("%Y-%m-%d %H:%M UTC") if row.last_run else "—"
            row_info = f", {row.last_row_count} rows" if row.last_row_count is not None else ""
            lines.append(f"- **Last run:** {last_run} ({row.last_status}{row_info})")
        else:
            lines.append("- **Last run:** Never")
        lines.append("")

    if found == 0:
        return "No reports are available for your role."

    return "\n".join(lines)
