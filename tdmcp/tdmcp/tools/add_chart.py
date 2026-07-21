"""Tool: add_chart — add a d3.js chart to an existing dashboard."""

from typing import Annotated

from pydantic import Field

from ._db_shared import enforce_db_access
from ._internal_api import call_internal


@enforce_db_access()
async def add_chart(
    dashboard_id: Annotated[
        str,
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
    # SQL validation, width clamping and the dashboard/database lookups all
    # happen server-side in the internal API; this tool just forwards the args.
    return await call_internal(
        "POST",
        f"/dashboards/{dashboard_id}/charts/",
        {
            "title": title,
            "sql_query": sql_query,
            "database": database,
            "d3_code": d3_code,
            "description": description,
            "width": width,
            "height": height,
            "position": position,
        },
    )
