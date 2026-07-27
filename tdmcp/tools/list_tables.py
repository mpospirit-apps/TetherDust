"""Tool: list_tables — discover available documented database tables."""

from . import get_shared_parser
from ._db_shared import get_allowed_doc_sources


async def list_tables() -> str:
    """List all documented database tables available to you. \
Use this to discover which tables exist before inspecting them with get_table_schema. \
Returns table names grouped by domain (e.g., Orders, Products, Users)."""
    parser = get_shared_parser()
    tables = parser.list_tables()

    allowed_sources = get_allowed_doc_sources()
    if allowed_sources is not None:
        tables = [t for t in tables if t.source_name in allowed_sources]

    if not tables:
        return (
            "No documented tables found. "
            "Please ensure documentation exists in the configured DOCS_PATH."
        )

    # Group tables by domain
    by_domain: dict[str, list[str]] = {}
    for table in tables:
        domain = table.domain or "Other"
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(table.name)

    # Format output
    lines = ["# Available Tables\n"]
    for domain, table_names in sorted(by_domain.items()):
        lines.append(f"## {domain}")
        for name in sorted(table_names):
            schema = parser.get_table_schema(name)
            desc = f" - {schema.description}" if schema and schema.description else ""
            lines.append(f"- **{name}**{desc}")
        lines.append("")

    return "\n".join(lines)
