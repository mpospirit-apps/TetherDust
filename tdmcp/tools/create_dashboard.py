"""Tool: create_dashboard — create a new dashboard in the Django database."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field

from ._admin_db import get_admin_engine

logger = logging.getLogger(__name__)


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
    from sqlalchemy import text

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    now = datetime.now(UTC)

    try:
        with engine.connect() as conn:
            # Check for duplicate name
            existing = conn.execute(
                text("SELECT id FROM core_dashboard WHERE name = :name"),
                {"name": name},
            ).fetchone()
            if existing:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"A dashboard named '{name}' already exists (id={existing[0]}).",
                    }
                )

            result = conn.execute(
                text(
                    "INSERT INTO core_dashboard (name, description, is_active, "
                    "auto_refresh, created_at, updated_at) "
                    "VALUES (:name, :description, true, false, :now, :now) "
                    "RETURNING id"
                ),
                {"name": name, "description": description, "now": now},
            )
            _row = result.fetchone()
            dashboard_id = _row[0] if _row is not None else None
            conn.commit()

        logger.info("Created dashboard '%s' (id=%d)", name, dashboard_id)
        return json.dumps(
            {
                "success": True,
                "dashboard_id": dashboard_id,
                "name": name,
            }
        )
    except Exception as e:
        logger.error("Failed to create dashboard '%s': %s", name, e, exc_info=True)
        return json.dumps({"success": False, "error": str(e)})
