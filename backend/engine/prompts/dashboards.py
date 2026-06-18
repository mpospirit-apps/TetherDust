"""Prompts for AI dashboard generation.

Call site: ``management/views/dashboard.py``. The static template text lives here;
the ``create_dashboard`` / ``add_chart`` tool instructions and the selected
database/doc names are appended by the caller, since they depend on request
context.
"""

DASHBOARD_TEMPLATES = {
    "overview": (
        "Create a dashboard showing key metrics and KPIs for the selected databases. "
        "Include charts for:\n"
        "- Summary counts and totals\n"
        "- Status distributions (pie or bar charts)\n"
        "- Recent activity trends (line or area charts)\n\n"
        "Each chart should tell a clear data story."
    ),
    "time_series": (
        "Create a dashboard with charts tracking trends and changes over time. "
        "Focus on:\n"
        "- Time-based aggregations (daily, weekly, monthly)\n"
        "- Growth or decline patterns\n"
        "- Comparisons across time periods\n\n"
        "Use line and area charts where appropriate."
    ),
    "comparison": (
        "Create a dashboard comparing metrics across categories or dimensions. "
        "Include:\n"
        "- Side-by-side comparisons (grouped bar charts)\n"
        "- Distribution breakdowns (pie or stacked bar charts)\n"
        "- Ranking visualizations\n\n"
        "Focus on making differences and patterns visually clear."
    ),
}
