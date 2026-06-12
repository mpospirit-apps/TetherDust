"""Tool: get_query_examples — retrieve pre-verified SQL query templates."""

from typing import Annotated

from pydantic import Field

from . import get_shared_parser
from ._db_shared import get_allowed_doc_sources


async def get_query_examples(
    table_name: Annotated[
        str | None, Field(description="Filter examples by table name (optional)")
    ] = None,
    use_case: Annotated[
        str | None,
        Field(description="Filter by use case description, e.g., 'reporting', 'lookup' (optional)"),
    ] = None,
) -> str:
    """IMPORTANT: Always call this tool BEFORE writing any new SQL query. \
This tool returns verified, working SQL examples for common use cases. \
Check if an existing example matches the user's request - if so, use or \
adapt it rather than writing from scratch. This ensures queries follow \
correct table/column naming conventions and include proper JOINs. \
Only write custom SQL if no relevant example exists."""
    parser = get_shared_parser()

    examples = parser.get_query_examples(table_name=table_name, use_case=use_case)

    allowed_sources = get_allowed_doc_sources()
    if allowed_sources is not None:
        examples = [ex for ex in examples if ex.source_name in allowed_sources]

    if not examples:
        msg = "No query examples found"
        filters = []
        if table_name:
            filters.append(f"table '{table_name}'")
        if use_case:
            filters.append(f"use case '{use_case}'")
        if filters:
            msg += f" matching {' and '.join(filters)}"
        msg += ". Try broader search terms or check available tables with list_tables."
        return msg

    # Format examples
    lines = ["# Query Examples\n"]

    if table_name or use_case:
        filters = []
        if table_name:
            filters.append(f"Table: {table_name}")
        if use_case:
            filters.append(f"Use case: {use_case}")
        lines.append(f"*Filtered by: {', '.join(filters)}*\n")

    for example in examples:
        lines.append(f"## {example.title}")

        if example.description:
            lines.append(f"{example.description}\n")

        if example.tables:
            lines.append(f"**Tables:** {', '.join(example.tables)}")

        if example.use_cases:
            lines.append(f"**Use cases:** {', '.join(example.use_cases)}")

        lines.append("\n```sql")
        lines.append(example.sql)
        lines.append("```\n")

        lines.append(f"*Source: {example.source_file}*\n")

    return "\n".join(lines)
