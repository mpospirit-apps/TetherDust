"""Tool: update_chart — modify an existing d3.js chart's editable fields."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field

from ..utils.db_service import QueryValidationError, validate_read_only_sql
from ._admin_db import get_admin_engine

logger = logging.getLogger(__name__)


def _validate_sql(sql: str) -> str | None:
    """Validate that SQL is a read-only SELECT query. Returns error message or None."""
    try:
        validate_read_only_sql(sql)
    except QueryValidationError as err:
        return str(err)
    return None


async def update_chart(
    chart_id: Annotated[
        int,
        Field(description="ID of the chart to modify."),
    ],
    title: Annotated[
        str | None,
        Field(description="New chart title. Omit to leave unchanged."),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New chart description. Omit to leave unchanged."),
    ] = None,
    sql_query: Annotated[
        str | None,
        Field(
            description=(
                "New read-only SELECT query. Omit to leave unchanged. "
                "The query result columns become the data fields available in d3_code. "
                "When sql_query changes, the cached data is cleared so the dashboard "
                "re-runs the query on the next load."
            )
        ),
    ] = None,
    d3_code: Annotated[
        str | None,
        Field(
            description=(
                "New raw d3.js code that renders the chart. Omit to leave unchanged. "
                "The code is called as a function with four arguments: 'data' (array "
                "of row objects from the SQL query), 'container' (DOM element to "
                "render into), 'd3' (the d3 library), and 'theme' (the current UI "
                "theme). Use d3.select(container) as the root element.\n\n"
                "COLOR RULES — THEME PALETTE ONLY (STRICT):\n"
                "You MUST use only the theme palette for ALL colors in the chart "
                "(fills, strokes, legends, gradients, categorical scales, sequential "
                "scales, highlights, annotations). Never hard-code hex/rgb/hsl/named "
                "colors (e.g. '#ff0000', 'steelblue', 'rgb(…)'), and never use d3's "
                "built-in color schemes by name (d3.schemeTableau10 literal hex values, "
                "d3.interpolateViridis, d3.schemeBlues, etc.) unless you read them via "
                "the 'theme' argument.\n\n"
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
                "Do NOT set explicit text/axis colors if you can omit them — SVG text "
                "and axis lines inherit theme-aware defaults from the host page "
                "(currentColor / --border). Omit fill/stroke on text elements unless "
                "you need a non-default color, and in that case still use theme.text / "
                "theme.textSec.\n\n"
                "BORDER RADIUS — DO NOT USE unless the user explicitly requests it:\n"
                "Do NOT apply border-radius (rx/ry attributes on rect elements or CSS "
                "border-radius) to chart shapes (bars, cells, areas, etc.) unless the "
                "user specifically asks for rounded corners. Default to sharp corners "
                "(no rx/ry)."
            )
        ),
    ] = None,
) -> str:
    """Update an existing d3.js chart. Only the fields you pass are modified; \
omitted fields stay as they were. Use this to iterate on a chart's title, \
description, SQL query, or d3 code without recreating it.

IMPORTANT — COLOR POLICY: Any d3_code you write MUST use ONLY the theme \
palette exposed via the 'theme' argument (theme.colors, theme.accent, \
theme.text, theme.textSec, theme.textMuted, theme.border, theme.surface). \
Hard-coded colors (hex, rgb, named) and d3's built-in color schemes with \
hard-coded values are NOT allowed. See the d3_code field description for \
details and examples.

IMPORTANT — BORDER RADIUS: Do NOT use rx/ry attributes or CSS border-radius \
on chart shapes unless the user explicitly asks for rounded corners."""
    from sqlalchemy import text

    updates: dict[str, object] = {}
    updated_fields: list[str] = []

    if title is not None:
        updates["title"] = title
        updated_fields.append("title")
    if description is not None:
        updates["description"] = description
        updated_fields.append("description")
    if sql_query is not None:
        sql_error = _validate_sql(sql_query)
        if sql_error:
            return json.dumps({"success": False, "error": sql_error})
        updates["sql_query"] = sql_query
        updated_fields.append("sql_query")
    if d3_code is not None:
        updates["custom_d3_code"] = d3_code
        updated_fields.append("d3_code")

    if not updates:
        return json.dumps(
            {
                "success": False,
                "error": "Nothing to update. Provide at least one of: title, "
                "description, sql_query, d3_code.",
            }
        )

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return json.dumps({"success": False, "error": str(e)})

    now = datetime.now(UTC)

    try:
        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT id FROM engine_chart WHERE id = :id"),
                {"id": chart_id},
            ).fetchone()
            if not existing:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Chart with id={chart_id} not found.",
                    }
                )

            set_clauses = [f"{col} = :{col}" for col in updates]
            set_clauses.append("updated_at = :now")

            # When sql_query changes, invalidate the cached data so the
            # dashboard re-runs the query on next load.
            if "sql_query" in updates:
                set_clauses.append("cached_data = CAST(:empty_cache AS jsonb)")
                set_clauses.append("last_refreshed_at = NULL")
                set_clauses.append("last_error = ''")
                updates["empty_cache"] = json.dumps({})

            params = {**updates, "id": chart_id, "now": now}

            conn.execute(
                text(f"UPDATE engine_chart SET {', '.join(set_clauses)} WHERE id = :id"),
                params,
            )
            conn.commit()

        logger.info("Updated chart id=%d fields=%s", chart_id, updated_fields)
        return json.dumps(
            {
                "success": True,
                "chart_id": chart_id,
                "updated_fields": updated_fields,
            }
        )
    except Exception as e:
        logger.error("Failed to update chart %d: %s", chart_id, e, exc_info=True)
        return json.dumps({"success": False, "error": str(e)})
