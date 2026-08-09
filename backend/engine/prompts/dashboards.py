"""Prompts for AI dashboard generation.

Call site: ``management/views/dashboard.py``. The static template text lives here;
the ``create_dashboard`` / ``add_chart`` tool instructions and the selected
database/doc names are appended by the caller, since they depend on request
context.
"""

DASHBOARD_TEMPLATES = {
    "overview": (
        "Create a dashboard giving an executive-level snapshot of the selected data: "
        "the 3-5 metrics that matter most, plus enough supporting detail to explain "
        "them.\n"
        "- Lead with KPI cards for the top metrics — each with a comparison (vs. "
        "prior period or target), not a bare number\n"
        "- Follow with status/composition breakdowns and recent activity trends\n\n"
        "Each chart should answer one clear question about the state of the data."
    ),
    "time_series": (
        "Create a dashboard focused on how metrics change over time.\n"
        "- Use time-based aggregation (daily/weekly/monthly — match the data's "
        "granularity) and make period-over-period comparisons explicit (this month "
        "vs. last, this year vs. last), not something the viewer has to infer\n"
        "- Keep each trend chart to a handful of series — split or aggregate rather "
        "than overlaying a dozen-plus lines\n\n"
        "Favor charts where direction (up/down) and rate of change are obvious at a "
        "glance."
    ),
    "comparison": (
        "Create a dashboard comparing metrics across categories or dimensions.\n"
        "- Rank categories highest-to-lowest rather than alphabetically, so the "
        "differences the dashboard exists to show are visible at a glance\n"
        "- Use grouped or stacked bars for side-by-side and composition breakdowns\n\n"
        "Focus on making differences and patterns visually clear, not just present."
    ),
}
