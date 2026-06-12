"""Tool: get_dashboard_charts — return chart definitions for a dashboard."""

import json
import logging
from typing import Annotated

from pydantic import Field

from ._admin_db import get_admin_engine
from ._db_shared import get_allowed_dashboards

logger = logging.getLogger(__name__)


async def get_dashboard_charts(
    dashboard_name: Annotated[
        str,
        Field(description="Name of the dashboard (from list_dashboards)."),
    ],
) -> str:
    """Return the charts in a dashboard, including each chart's title, type, \
description, and SQL query.

Use list_dashboards first to discover available dashboard names. This tool \
gives you the full chart definitions so you can describe what data the \
dashboard visualises or answer questions about specific charts."""
    from sqlalchemy import text

    if not dashboard_name:
        return "Error: dashboard_name parameter is required"

    allowed = get_allowed_dashboards()
    if allowed is not None and dashboard_name not in allowed:
        return f"Access denied: dashboard '{dashboard_name}' is not available for your role."

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    try:
        with engine.connect() as conn:
            # Verify the dashboard exists and is active
            dashboard = conn.execute(
                text(
                    "SELECT id, name, description FROM core_dashboard "
                    "WHERE name = :name AND is_active = true"
                ),
                {"name": dashboard_name},
            ).fetchone()

            if dashboard is None:
                return f"Dashboard '{dashboard_name}' not found or is inactive."

            charts = conn.execute(
                text(
                    "SELECT title, description, chart_type, sql_query, "
                    "       chart_spec, width "
                    "FROM core_chart "
                    "WHERE dashboard_id = :dashboard_id "
                    "ORDER BY id"
                ),
                {"dashboard_id": dashboard.id},
            ).fetchall()
    except Exception as e:
        logger.error(
            "Failed to get charts for dashboard '%s': %s", dashboard_name, e, exc_info=True
        )
        return f"Error retrieving dashboard charts: {e}"

    if not charts:
        return f"Dashboard '{dashboard_name}' has no charts."

    lines = [f"# Dashboard: {dashboard_name}\n"]
    if dashboard.description:
        lines.append(f"{dashboard.description}\n")

    lines.append(f"**{len(charts)} chart(s):**\n")

    for i, chart in enumerate(charts, 1):
        lines.append(f"## Chart {i}: {chart.title}")
        if chart.description:
            lines.append(chart.description)
        lines.append(f"- **Type:** {chart.chart_type}")

        # Surface key spec fields without dumping the full JSON
        spec = chart.chart_spec
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except Exception:
                spec = {}
        if isinstance(spec, dict) and spec:
            x = spec.get("x_axis") or spec.get("x")
            y = spec.get("y_axis") or spec.get("y")
            if x:
                lines.append(f"- **X axis:** {x}")
            if y:
                lines.append(f"- **Y axis:** {y}")

        lines.append(f"- **SQL query:**\n```sql\n{chart.sql_query.strip()}\n```")
        lines.append("")

    return "\n".join(lines)
