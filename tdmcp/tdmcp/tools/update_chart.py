"""Tool: update_chart — modify an existing d3.js chart's editable fields."""

from typing import Annotated

from pydantic import Field

from ._internal_api import call_internal


async def update_chart(
    chart_id: Annotated[
        str,
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
    # Forward only the provided fields. SQL validation and cache invalidation on
    # an sql_query change are handled server-side by the internal API.
    payload: dict[str, str] = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if sql_query is not None:
        payload["sql_query"] = sql_query
    if d3_code is not None:
        payload["d3_code"] = d3_code

    return await call_internal("PATCH", f"/charts/{chart_id}/", payload)
