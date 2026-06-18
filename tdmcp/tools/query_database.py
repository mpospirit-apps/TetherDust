"""Tool: query_database — execute read-only SQL queries."""

from typing import Annotated

from pydantic import Field

from ..utils.db_service import QueryValidationError
from ._db_shared import enforce_db_access, get_db_service, get_max_row_limit


@enforce_db_access()
async def query_database(
    sql: Annotated[str, Field(description="SQL SELECT query to execute")],
    database: Annotated[
        str | None,
        Field(
            description=(
                "Name of the database connection to use (from list_databases). "
                "If not specified, uses the first configured database."
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum rows to return (default 100, max 1000)", default=100),
    ] = 100,
) -> str:
    """Execute a read-only SQL query against the database and return results.

REQUIREMENTS:
1. ALWAYS call get_query_examples first to check for existing query patterns
2. Only SELECT statements are allowed (no INSERT, UPDATE, DELETE, DROP, etc.)
3. Results are limited to prevent large data transfers (default 100 rows)
4. Use get_table_schema if unsure about column names or types

If the query fails, check the error message and verify table/column names \
using get_table_schema before retrying."""
    if not sql:
        return "Error: sql parameter is required"

    # Database access is enforced by the @enforce_db_access decorator.

    # Enforce max row limit
    max_limit = get_max_row_limit()
    if max_limit is not None:
        limit = min(limit, max_limit)

    db_service = get_db_service()

    try:
        rows, row_count = db_service.execute_query(
            sql=sql,
            database=database,
            limit=limit,
        )
    except QueryValidationError as e:
        return f"Query validation error: {e}"
    except ValueError as e:
        return f"Configuration error: {e}"
    except Exception as e:
        return (
            f"Query execution error: {e}\n\nVerify table and column names using get_table_schema."
        )

    if not rows:
        return "Query returned no results."

    # Format results as markdown table
    lines = [f"# Query Results ({row_count} rows)\n"]

    # Get column names from first row
    columns = list(rows[0].keys())

    # Build header
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

    # Build rows
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col)
            if val is None:
                values.append("NULL")
            else:
                # Escape pipe characters in values
                str_val = str(val).replace("|", "\\|")
                # Truncate long values
                if len(str_val) > 50:
                    str_val = str_val[:47] + "..."
                values.append(str_val)
        lines.append("| " + " | ".join(values) + " |")

    # Add note if results were limited
    if row_count == limit:
        lines.append(f"\n*Results limited to {limit} rows. Increase limit parameter for more.*")

    return "\n".join(lines)
