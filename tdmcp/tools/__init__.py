"""MCP tool implementations for TetherDust.

Each tool lives in its own module as a plain async function.
Provides a shared DocumentationParser instance used by documentation-related tools.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils.markdown_parser import DocumentationParser, DocumentationSourceConfig

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Shared parser instance (lazy-initialized, used by doc/example tools)
_shared_parser: DocumentationParser | None = None


def _load_sources_from_admin_db() -> list[DocumentationSourceConfig] | None:
    """Load documentation sources directly from PostgreSQL via ADMIN_DATABASE_URL.

    Used by the MCP container which has no Django but can reach the shared DB.
    Returns None if ADMIN_DATABASE_URL is not set or the query fails.
    """
    db_url = os.environ.get("ADMIN_DATABASE_URL", "").strip()
    docs_dir = os.environ.get("TETHERDUST_DOCUMENTATIONS_DIR", "").strip()
    if not db_url or not docs_dir:
        return None

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT folder_name, description "
                    "FROM engine_documentationsource "
                    "WHERE is_active = true ORDER BY folder_name"
                )
            ).fetchall()
        engine.dispose()

        return [
            DocumentationSourceConfig(
                name=row.folder_name,
                path=str(Path(docs_dir) / row.folder_name),
                description=row.description or "",
            )
            for row in rows
        ]
    except Exception as exc:
        logger.warning("Failed to load sources from ADMIN_DATABASE_URL: %s", exc)
        return None


def get_shared_parser() -> DocumentationParser:
    """Get or create the shared documentation parser.

    Resolves documentation sources from (in order):
    1. ADMIN_DATABASE_URL direct query (MCP container path)
    2. Parser's built-in resolution: Django ORM → TETHERDUST_DOCUMENTATIONS_DIR → DOCS_PATH
    """
    global _shared_parser
    if _shared_parser is None:
        logger.info("[DEBUG PARSER] Initializing shared DocumentationParser...")

        sources = _load_sources_from_admin_db()
        if sources is not None:
            logger.info("[DEBUG PARSER] Loaded %d sources from ADMIN_DATABASE_URL", len(sources))
            _shared_parser = DocumentationParser(sources=sources)
        else:
            _shared_parser = DocumentationParser()

        _shared_parser._ensure_loaded()
        logger.info("[DEBUG PARSER] Sources loaded: %s", [s.name for s in _shared_parser._sources])
        logger.info(
            "[DEBUG PARSER] Tables cached: %d",
            len(_shared_parser._table_cache),
        )
        for s in _shared_parser._sources:
            source_path = s.path
            exists = Path(source_path).exists()
            is_dir = Path(source_path).is_dir() if exists else False
            logger.info(
                "[DEBUG PARSER]   source: name=%s, path=%s, exists=%s, is_dir=%s",
                s.name,
                source_path,
                exists,
                is_dir,
            )
    return _shared_parser


def iter_tool_handlers() -> list[Callable[..., object]]:
    """The concrete list of tool handler functions, in a stable order.

    Single source of truth for "what tools exist": ``register_tools`` (which
    exposes them over MCP) and the Django backend's built-in-server seeding
    (``engine.builtin_mcp``, which mirrors each tool's real name/docstring
    into the admin DB) both read from this instead of keeping their own
    separately-maintained list.
    """
    from .add_chart import add_chart
    from .create_dashboard import create_dashboard
    from .create_documentation import create_documentation
    from .get_codebase_tree import get_codebase_tree
    from .get_dashboard_charts import get_dashboard_charts
    from .get_report_data import get_report_data
    from .get_table_schema import get_table_schema
    from .get_tether_graph import get_tether_graph
    from .list_codebases import list_codebases
    from .list_dashboards import list_dashboards
    from .list_databases import list_databases
    from .list_reports import list_reports
    from .list_tables import list_tables
    from .list_tethers import list_tethers
    from .query_database import query_database
    from .read_codebase_file import read_codebase_file
    from .save_tether_graph import save_tether_graph
    from .search_codebase import search_codebase
    from .search_docs import search_docs
    from .update_chart import update_chart

    return [
        list_tables,
        get_table_schema,
        search_docs,
        list_databases,
        query_database,
        create_documentation,
        create_dashboard,
        add_chart,
        update_chart,
        save_tether_graph,
        list_codebases,
        get_codebase_tree,
        read_codebase_file,
        search_codebase,
        list_reports,
        get_report_data,
        list_dashboards,
        get_dashboard_charts,
        list_tethers,
        get_tether_graph,
    ]


def register_tools(mcp: FastMCP) -> None:
    """Register all TetherDust tools on the FastMCP server instance."""
    for handler in iter_tool_handlers():
        mcp.tool()(handler)


def _json_schema_type_label(schema: dict[str, object]) -> str:
    """A short, human-readable type label from a JSON Schema property.

    Handles the two shapes FastMCP emits for tool parameters: a plain
    ``{"type": "..."}`` and an optional/nullable ``{"anyOf": [...]}``.
    """
    schema_type = schema.get("type")
    if not schema_type:
        any_of = schema.get("anyOf")
        if isinstance(any_of, list):
            types = [
                s.get("type") for s in any_of if isinstance(s, dict) and s.get("type") != "null"
            ]
            schema_type = types[0] if types else "any"
        else:
            schema_type = "any"

    if schema_type == "array":
        items = schema.get("items")
        item_type = items.get("type", "any") if isinstance(items, dict) else "any"
        return f"array<{item_type}>"
    return str(schema_type)


def describe_tool_schema(handler: Callable[..., object]) -> dict[str, object]:
    """The real parameter/return schema for a tool handler.

    Built via ``mcp.server.fastmcp``'s own ``Tool.from_function`` — the exact
    code path FastMCP uses when registering a tool — rather than a hand-rolled
    re-parse of each function's ``Annotated``/``Field`` metadata, so this can
    never drift from what the agent is actually sent.
    """
    import inspect

    from mcp.server.fastmcp.tools.base import Tool as MCPTool

    mcp_tool = MCPTool.from_function(handler)
    schema = mcp_tool.parameters
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    parameters = [
        {
            "name": name,
            "type": _json_schema_type_label(prop),
            "description": prop.get("description", ""),
            "required": name in required,
            "default": prop.get("default"),
        }
        for name, prop in properties.items()
    ]

    return_annotation = inspect.signature(handler).return_annotation
    returns = getattr(return_annotation, "__name__", None) or str(return_annotation)

    return {"parameters": parameters, "returns": returns}
