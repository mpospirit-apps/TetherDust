"""Tool: add_chart — add a d3.js chart to an existing dashboard."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field

from ..utils.db_service import QueryValidationError, validate_read_only_sql
from ._admin_db import get_admin_engine
from ._db_shared import enforce_db_access

logger = logging.getLogger(__name__)


def _validate_sql(sql: str) -> str | None:
    """Validate that SQL is a read-only SELECT query. Returns error message or None."""
    try:
        validate_read_only_sql(sql)
    except QueryValidationError as err:
        return str(err)
    return None


@enforce_db_access()
async def add_chart(
    dashboard_id: Annotated[
        int,
        Field(description="ID of the dashboard (from create_dashboard response)."),
    ],
    title: Annotated[
        str,
        Field(description="Chart title displayed above the visualization."),
    ],
    sql_query: Annotated[
        str,
        Field(
            description="Read-only SELECT query that produces the chart data. "
            "The query result columns become the data fields available in d3_code."
        ),
    ],
    database: Annotated[
        str,
        Field(description="Name of the database connection to run the query against."),
    ],
    d3_code: Annotated[
        str,
        Field(
            description=(
                "Raw d3.js code that renders the chart. The code is called as a function "
                "with four arguments: 'data' (array of row objects from the SQL query), "
                "'container' (DOM element to render into), 'd3' (the d3 library), and "
                "'theme' (the current UI theme). Use d3.select(container) as the root element.\n\n"
                "COLOR RULES — THEME PALETTE ONLY (STRICT):\n"
                "You MUST use only the theme palette for ALL colors in the chart "
                "(fills, strokes, legends, gradients, categorical scales, sequential scales, "
                "highlights, annotations). Never hard-code hex/rgb/hsl/named colors "
                "(e.g. '#ff0000', 'steelblue', 'rgb(…)'), and never use d3's built-in color "
                "schemes by name (d3.schemeTableau10 literal hex values, d3.interpolateViridis, "
                "d3.schemeBlues, etc.) unless you read them via the 'theme' argument.\n\n"
                "The 'theme' argument provides:\n"
                "  theme.colors     — array of categorical palette colors"  # noqa: E501
                " (use for series/categories)\n"
                "  theme.accent     — the current accent color (single-hue highlight)\n"
                "  theme.text       — primary text color (use for labels, titles)\n"
                "  theme.textSec    — secondary text color (use for axis tick labels)\n"
                "  theme.textMuted  — muted text color\n"
                "  theme.border     — border/grid/axis line color\n"
                "  theme.surface    — background surface color\n"
                "  theme.mode       — 'light' or 'dark'\n\n"
                "Usage examples:\n"
                "  • Categorical scale:  d3.scaleOrdinal().range(theme.colors)\n"
                "  • Single color bar:   .attr('fill', theme.colors[0])\n"
                "  • Accent highlight:   .attr('stroke', theme.accent)\n"
                "  • Sequential scale:   d3.scaleLinear()"  # noqa: E501
                ".range([theme.colors[1], theme.colors[0]])\n"
                "  • Axis text:          .attr('fill', theme.textSec)\n\n"
                "Do NOT set explicit text/axis colors if you can omit them — SVG text and axis "
                "lines inherit theme-aware defaults from the host page (currentColor / --border). "
                "Omit fill/stroke on text elements unless you need a non-default color, and in "
                "that case still use theme.text / theme.textSec.\n\n"
                "BORDER RADIUS — DO NOT USE unless the user explicitly requests it:\n"
                "Do NOT apply border-radius (rx/ry attributes on rect elements or CSS "
                "border-radius) to chart shapes (bars, cells, areas, etc.) unless the user "
                "specifically asks for rounded corners. Default to sharp corners (no rx/ry)."
            )
        ),
    ],
    description: Annotated[
        str,
        Field(description="Brief description of what this chart shows."),
    ] = "",
    width: Annotated[
        int,
        Field(
            description="Grid column span out of 12. Options: 3 (quarter), 4 (third), "
            "6 (half), 8 (two-thirds), 12 (full width). Default: 6."
        ),
    ] = 6,
    height: Annotated[
        int,
        Field(description="Chart height in pixels. Default: 300."),
    ] = 300,
    position: Annotated[
        int,
        Field(
            description="Ordering position within the dashboard grid. Lower = first. Default: 0."
        ),
    ] = 0,
) -> str:
    """Add a d3.js chart to an existing dashboard. The chart's SQL query runs \
against the specified database and the d3.js code renders the results. \
Call create_dashboard first to get a dashboard_id.

IMPORTANT — COLOR POLICY: The d3_code MUST use ONLY the theme palette \
exposed via the 'theme' argument (theme.colors, theme.accent, theme.text, \
theme.textSec, theme.textMuted, theme.border, theme.surface). Hard-coded \
colors (hex, rgb, named) and d3's built-in color schemes with hard-coded \
values are NOT allowed. See the d3_code field description for details and \
examples.

IMPORTANT — BORDER RADIUS: Do NOT use rx/ry attributes or CSS border-radius \
on chart shapes unless the user explicitly asks for rounded corners."""
    from sqlalchemy import text

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return json.dumps({"success": False, "error": str(e)})

    # Validate SQL
    sql_error = _validate_sql(sql_query)
    if sql_error:
        return json.dumps({"success": False, "error": sql_error})

    # Validate width
    valid_widths = {3, 4, 6, 8, 12}
    if width not in valid_widths:
        width = 6

    now = datetime.now(UTC)

    try:
        with engine.connect() as conn:
            # Verify dashboard exists
            dashboard = conn.execute(
                text("SELECT id FROM engine_dashboard WHERE id = :id"),
                {"id": dashboard_id},
            ).fetchone()
            if not dashboard:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Dashboard with id={dashboard_id} not found.",
                    }
                )

            # Resolve database name to id
            db_row = conn.execute(
                text(
                    "SELECT id FROM engine_databaseconnection "
                    "WHERE name = :name AND is_active = true"
                ),
                {"name": database},
            ).fetchone()
            if not db_row:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Database connection '{database}' not found or inactive.",
                    }
                )
            database_id = db_row[0]

            result = conn.execute(
                text(
                    "INSERT INTO engine_chart "
                    "(dashboard_id, title, description, sql_query, chart_type, chart_spec, "
                    "custom_d3_code, database_id, position, width, height, is_active, "
                    "cached_data, last_error, created_at, updated_at) "
                    "VALUES (:dashboard_id, :title, :description, :sql_query, 'custom', "
                    ":chart_spec, :d3_code, :database_id, :position, :width, :height, "
                    "true, :cached_data, '', :now, :now) "
                    "RETURNING id"
                ),
                {
                    "dashboard_id": dashboard_id,
                    "title": title,
                    "description": description,
                    "sql_query": sql_query,
                    "chart_spec": json.dumps({}),
                    "d3_code": d3_code,
                    "database_id": database_id,
                    "position": position,
                    "width": width,
                    "height": height,
                    "cached_data": json.dumps({}),
                    "now": now,
                },
            )
            _row = result.fetchone()
            chart_id = _row[0] if _row is not None else None
            conn.commit()

        logger.info("Added chart '%s' (id=%d) to dashboard %d", title, chart_id, dashboard_id)
        return json.dumps(
            {
                "success": True,
                "chart_id": chart_id,
                "title": title,
                "dashboard_id": dashboard_id,
            }
        )
    except Exception as e:
        logger.error("Failed to add chart '%s': %s", title, e, exc_info=True)
        return json.dumps({"success": False, "error": str(e)})
