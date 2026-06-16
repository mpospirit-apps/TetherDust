"""Tool: get_report_data — run a report's SQL query and return live results."""

import logging
from typing import Annotated

from pydantic import Field

from ..utils.db_service import QueryValidationError
from ._admin_db import get_admin_engine
from ._db_shared import (
    get_allowed_reports,
    get_db_service,
    get_max_row_limit,
)

logger = logging.getLogger(__name__)


async def get_report_data(
    report_name: Annotated[
        str,
        Field(description="Name of the report to run (from list_reports)."),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum rows to return (default 100, max 1000)", default=100),
    ] = 100,
) -> str:
    """Run a report's SQL query against its configured database and return live results.

Use list_reports first to discover available report names. The query is the \
same read-only SELECT stored in the report definition — no writes are possible. \
Results are returned as a markdown table."""
    from sqlalchemy import text

    if not report_name:
        return "Error: report_name parameter is required"

    allowed = get_allowed_reports()
    if allowed is not None and report_name not in allowed:
        return f"Access denied: report '{report_name}' is not available for your role."

    try:
        engine = get_admin_engine()
    except RuntimeError as e:
        return f"Error: {e}"

    # Look up the report definition and its database connection name
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT rd.sql_query, dc.name AS database_name "
                    "FROM engine_reportdefinition rd "
                    "LEFT JOIN engine_databaseconnection dc ON dc.id = rd.database_id "
                    "WHERE rd.name = :name AND rd.is_active = true"
                ),
                {"name": report_name},
            ).fetchone()
    except Exception as e:
        logger.error("Failed to look up report '%s': %s", report_name, e, exc_info=True)
        return f"Error looking up report: {e}"

    if row is None:
        return f"Report '{report_name}' not found or is inactive."

    sql_query = row.sql_query
    database_name = row.database_name

    # Enforce max row limit from the user's role
    max_limit = get_max_row_limit()
    if max_limit is not None:
        limit = min(limit, max_limit)

    db_service = get_db_service()
    try:
        rows, row_count = db_service.execute_query(
            sql=sql_query,
            database=database_name,
            limit=limit,
        )
    except QueryValidationError as e:
        return f"Report query validation error: {e}"
    except ValueError as e:
        return f"Configuration error: {e}"
    except Exception as e:
        return f"Report query execution error: {e}"

    if not rows:
        return f"Report '{report_name}' returned no results."

    lines = [f"# Report: {report_name} ({row_count} rows)\n"]

    columns = list(rows[0].keys())
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

    for data_row in rows:
        values = []
        for col in columns:
            val = data_row.get(col)
            if val is None:
                values.append("NULL")
            else:
                str_val = str(val).replace("|", "\\|")
                if len(str_val) > 50:
                    str_val = str_val[:47] + "..."
                values.append(str_val)
        lines.append("| " + " | ".join(values) + " |")

    if row_count == limit:
        lines.append(f"\n*Results limited to {limit} rows. Increase limit parameter for more.*")

    return "\n".join(lines)
