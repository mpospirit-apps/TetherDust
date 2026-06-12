"""Tool: get_table_schema — get detailed schema for a database table."""

from typing import Annotated

from pydantic import Field

from . import get_shared_parser
from ._db_shared import get_allowed_doc_sources


async def get_table_schema(
    table_name: Annotated[str, Field(description="Name of the table (e.g., 'Order', 'Customer')")],
) -> str:
    """Get the complete schema documentation for a database table including \
all columns, their data types, descriptions, enum/status mappings, and \
example values. Use this tool when the user asks about table structure, \
column meanings, or needs to understand what data a table contains before \
writing queries."""
    parser = get_shared_parser()

    if not table_name:
        return "Error: table_name parameter is required"

    table = parser.get_table_schema(table_name)

    # Check doc source access
    allowed_sources = get_allowed_doc_sources()
    if table and allowed_sources is not None and table.source_name not in allowed_sources:
        table = None

    if not table:
        # Suggest similar tables
        all_tables = parser.list_tables()
        if allowed_sources is not None:
            all_tables = [t for t in all_tables if t.source_name in allowed_sources]
        suggestions = [t.name for t in all_tables if table_name.lower() in t.name.lower()]
        msg = f"Table '{table_name}' not found in documentation."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        return msg

    # Format schema as markdown
    lines = [f"# {table.name}"]

    if table.domain:
        lines.append(f"**Domain:** {table.domain}")

    if table.description:
        lines.append(f"\n{table.description}\n")

    if table.columns:
        lines.append("## Columns\n")
        lines.append("| Column | Type | Nullable | Description |")
        lines.append("|--------|------|----------|-------------|")

        for col in table.columns:
            nullable = "Yes" if col.nullable else "No"
            desc = col.description
            if col.enum_values:
                desc += f" Enum: {', '.join(col.enum_values)}"
            lines.append(f"| {col.name} | {col.data_type} | {nullable} | {desc} |")

    lines.append(f"\n*Source: {table.source_file}*")

    return "\n".join(lines)
