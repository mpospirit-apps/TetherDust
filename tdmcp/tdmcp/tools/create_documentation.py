"""Tool: create_documentation — write documentation files with optional DB introspection."""

import logging
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from ._db_shared import check_database_access, get_allowed_doc_sources, get_db_service

logger = logging.getLogger(__name__)


def _get_documentations_dir() -> Path:
    """Resolve the root documentations directory."""
    docs_dir = os.environ.get("TETHERDUST_DOCUMENTATIONS_DIR", "").strip()
    if docs_dir:
        return Path(docs_dir)
    return Path("sources/docs")


def _introspect_databases(
    database_names: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """Introspect specified databases and return schema information as markdown.

    Returns (markdown_text, errors) where errors is a list of
    {"database": name, "error": message} dicts for any failures.
    """
    from sqlalchemy import inspect

    db_service = get_db_service()
    parts: list[str] = []
    errors: list[dict[str, Any]] = []

    for db_name in database_names:
        # Per-name enforcement (partial allow): a disallowed database is skipped
        # rather than failing the whole call. Uses the same primitive as the
        # @enforce_db_access decorator so the rule stays in one place.
        if check_database_access(db_name) is not None:
            parts.append(f"## Database: {db_name}\n(Access denied)\n")
            continue

        config = db_service.get_database(db_name)
        if not config:
            parts.append(f"## Database: {db_name}\n(Not found)\n")
            continue

        parts.append(f"## Database: {db_name} ({config.engine})")
        if config.description:
            parts.append(config.description)

        try:
            if config.engine == "clickhouse":
                import clickhouse_connect

                client = clickhouse_connect.get_client(
                    host=config.host,
                    port=config.port or 8123,
                    username=config.username or "default",
                    password=config.password or "",
                    database=config.database or "default",
                    connect_timeout=10,
                    send_receive_timeout=10,
                )
                result = client.query(
                    "SELECT table, name, type FROM system.columns "
                    f"WHERE database = '{config.database or 'default'}' "
                    "ORDER BY table, position"
                )
                current_table = None
                for row in result.result_rows:
                    table, col_name, col_type = row[0], row[1], row[2]
                    if table != current_table:
                        parts.append(f"\n### Table: {table}")
                        current_table = table
                    parts.append(f"  - {col_name} ({col_type})")
                client.close()
            else:
                engine = db_service._get_engine(db_name)
                insp = inspect(engine)
                for table_name in sorted(insp.get_table_names()):
                    parts.append(f"\n### Table: {table_name}")
                    for col in insp.get_columns(table_name):
                        nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                        parts.append(f"  - {col['name']} ({col['type']}, {nullable})")
        except Exception as e:
            logger.error("Error introspecting database %s: %s", db_name, e, exc_info=True)
            parts.append("\n(Database unavailable — skipped)")
            errors.append({"database": db_name, "error": str(e)})

        parts.append("")

    return "\n".join(parts), errors


def _list_existing_docs(source_names: list[str]) -> str:
    """List existing documentation sources as wiki-links instead of verbatim content.

    The agent still has full access to reference docs through search_docs,
    get_table_schema, etc. during generation — this only affects what gets
    appended to the output file.
    """
    allowed = get_allowed_doc_sources()
    parts: list[str] = []
    docs_dir = _get_documentations_dir()

    for source_name in source_names:
        if allowed is not None and source_name not in allowed:
            parts.append(f"## Documentation: {source_name}\n(Access denied)\n")
            continue

        source_path = docs_dir / source_name
        if not source_path.exists() or not source_path.is_dir():
            parts.append(f"## Documentation: {source_name}\n(Not found)\n")
            continue

        parts.append(f"## Related Documentation: {source_name}")
        for doc_file in sorted(source_path.rglob("*.md")):
            rel_path = doc_file.relative_to(docs_dir)
            parts.append(f"- [[{rel_path}|{doc_file.stem}]]")
        parts.append("")

    return "\n".join(parts)


async def create_documentation(
    destination: Annotated[
        str,
        Field(
            description="Target folder path within the documentations directory "
            "(e.g., 'Database Documentation', 'Query Examples/subfolder'). "
            "Created automatically if it doesn't exist."
        ),
    ],
    filename: Annotated[
        str,
        Field(
            description="Name for the documentation file (e.g., 'users_tables'). "
            "The .md extension is added automatically if not present."
        ),
    ],
    content: Annotated[
        str,
        Field(description="The markdown content to write to the documentation file."),
    ],
    databases: Annotated[
        list[str] | None,
        Field(
            description="Optional list of database names to introspect. "
            "If provided, a 'Database Schema Reference' section with full "
            "table/column details is appended to the content."
        ),
    ] = None,
    reference_docs: Annotated[
        list[str] | None,
        Field(
            description="Optional list of existing documentation source names to include "
            "as reference material at the end of the document."
        ),
    ] = None,
) -> str:
    """Create or overwrite a documentation file in the documentations directory. \
Use this tool after gathering information (via list_tables, get_table_schema, \
search_docs, query_database, etc.) and generating documentation content. \
Optionally introspects databases and includes existing docs as reference appendices. \
The new documentation becomes immediately available to search_docs and other doc tools."""
    docs_dir = _get_documentations_dir()

    if not docs_dir.exists():
        return f"Error: documentations directory '{docs_dir}' does not exist."

    # Sanitize destination — allow forward slashes for subdirs, block traversal
    destination = destination.replace("\\", "/")
    destination = "/".join(part for part in destination.split("/") if part and part != "..")
    if not destination:
        return "Error: invalid destination folder path."

    dest_path = docs_dir / destination

    # Verify resolved path is within docs_dir (prevent traversal via symlinks)
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
        resolved = dest_path.resolve()
        if not resolved.is_relative_to(docs_dir.resolve()):
            return "Error: destination resolves outside the documentations directory."
    except OSError as e:
        return f"Error creating destination directory: {e}"

    # Sanitize filename
    safe_name = filename.replace("/", "").replace("\\", "").strip()
    if not safe_name:
        return "Error: invalid filename."
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    # Build final content
    final_parts = [content]

    # Append database schema introspection if requested
    introspect_errors: list[dict[str, Any]] = []
    if databases:
        schema_info, introspect_errors = _introspect_databases(databases)
        if schema_info.strip():
            final_parts.append("\n\n---\n\n# Database Schema Reference\n")
            final_parts.append(schema_info)

    # Append existing documentation references as wiki-links if requested
    if reference_docs:
        doc_info = _list_existing_docs(reference_docs)
        if doc_info.strip():
            final_parts.append("\n\n---\n\n# Related Documentation\n")
            final_parts.append(doc_info)

    final_content = "\n".join(final_parts)

    # Write the file
    filepath = dest_path / safe_name
    try:
        filepath.write_text(final_content, encoding="utf-8")
    except OSError as e:
        return f"Error writing file: {e}"

    # Reload the shared documentation parser so new docs are immediately searchable
    from . import _shared_parser

    if _shared_parser is not None:
        _shared_parser._loaded = False
        logger.info("Documentation parser cache invalidated after creating %s", filepath)

    file_size = filepath.stat().st_size
    result_lines = [
        "Documentation created successfully.",
        f"- Path: {filepath.relative_to(docs_dir)}",
        f"- Size: {file_size:,} bytes",
        f"- Folder: {destination}",
    ]
    if introspect_errors:
        import json as _json

        result_lines.append(f"- Errors: {_json.dumps(introspect_errors)}")
    result_lines.append(
        "The documentation is now available via search_docs and other documentation tools."
    )
    return "\n".join(result_lines)
