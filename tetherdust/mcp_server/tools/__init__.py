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
                    "SELECT folder_name, description, file_patterns "
                    "FROM core_documentationsource "
                    "WHERE is_active = true ORDER BY folder_name"
                )
            ).fetchall()
        engine.dispose()

        return [
            DocumentationSourceConfig(
                name=row.folder_name,
                path=str(Path(docs_dir) / row.folder_name),
                description=row.description or "",
                file_patterns=row.file_patterns if row.file_patterns else ["*.md"],
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

        # Try loading sources from the admin DB so file_patterns are respected
        sources = _load_sources_from_admin_db()
        if sources is not None:
            logger.info("[DEBUG PARSER] Loaded %d sources from ADMIN_DATABASE_URL", len(sources))
            _shared_parser = DocumentationParser(sources=sources)
        else:
            _shared_parser = DocumentationParser()

        _shared_parser._ensure_loaded()
        logger.info("[DEBUG PARSER] Sources loaded: %s", [s.name for s in _shared_parser._sources])
        logger.info(
            "[DEBUG PARSER] Tables cached: %d, Examples cached: %d",
            len(_shared_parser._table_cache),
            len(_shared_parser._examples_cache),
        )
        for s in _shared_parser._sources:
            source_path = s.path
            exists = Path(source_path).exists()
            is_dir = Path(source_path).is_dir() if exists else False
            logger.info(
                "[DEBUG PARSER]   source: name=%s, path=%s, exists=%s, is_dir=%s, patterns=%s",
                s.name,
                source_path,
                exists,
                is_dir,
                s.file_patterns,
            )
    return _shared_parser


def register_tools(mcp: FastMCP) -> None:
    """Register all TetherDust tools on the FastMCP server instance."""
    from .add_chart import add_chart
    from .create_dashboard import create_dashboard
    from .create_documentation import create_documentation
    from .get_codebase_tree import get_codebase_tree
    from .get_dashboard_charts import get_dashboard_charts
    from .get_query_examples import get_query_examples
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

    handlers: list[Callable[..., object]] = [
        list_tables,
        get_table_schema,
        search_docs,
        get_query_examples,
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
    for handler in handlers:
        mcp.tool()(handler)
