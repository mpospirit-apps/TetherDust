"""Tool: create_dashboard — create a new dashboard via the backend internal API."""

from typing import Annotated

from pydantic import Field

from ._internal_api import call_internal


async def create_dashboard(
    name: Annotated[
        str,
        Field(description="Unique name for the dashboard (e.g., 'Sales Overview Q1 2026')."),
    ],
    description: Annotated[
        str,
        Field(description="Brief description of what this dashboard shows."),
    ] = "",
) -> str:
    """Create a new dashboard container. Call this first, then use add_chart \
to add individual charts to the dashboard. Returns the dashboard_id needed \
for add_chart calls."""
    return await call_internal(
        "POST",
        "/dashboards/",
        {"name": name, "description": description},
    )
