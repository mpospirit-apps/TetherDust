"""Tool: list_dashboards — list accessible dashboards with their charts."""

import logging

from ._admin_db import get_admin_engine
from ._db_shared import get_allowed_dashboards

logger = logging.getLogger(__name__)


async def list_dashboards() -> str:
    """List all dashboards the current user can access.

Use this tool to discover available dashboards before calling \
get_dashboard_charts. Returns each dashboard's name, description, and the \
number of charts it contains."""
    from sqlalchemy import text

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    allowed = get_allowed_dashboards()

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.name, d.description, COUNT(c.id) AS chart_count "
                    "FROM engine_dashboard d "
                    "LEFT JOIN engine_chart c ON c.dashboard_id = d.id "
                    "WHERE d.is_active = true "
                    "GROUP BY d.id, d.name, d.description "
                    "ORDER BY d.name"
                )
            ).fetchall()
    except Exception as e:
        logger.error("Failed to list dashboards: %s", e, exc_info=True)
        return f"Error listing dashboards: {e}"

    if not rows:
        return "No active dashboards found."

    lines = ["# Available Dashboards\n"]
    found = 0
    for row in rows:
        name = row.name
        if allowed is not None and name not in allowed:
            continue
        found += 1
        lines.append(f"## {name}")
        if row.description:
            lines.append(row.description)
        chart_word = "chart" if row.chart_count == 1 else "charts"
        lines.append(f"- **Charts:** {row.chart_count} {chart_word}")
        lines.append("")

    if found == 0:
        return "No dashboards are available for your role."

    return "\n".join(lines)
