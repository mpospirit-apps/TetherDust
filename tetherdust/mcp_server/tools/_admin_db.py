"""Shared helper for MCP tools that write to Django's admin database.

Uses ADMIN_DATABASE_URL with SQLAlchemy — the same connection pattern used by
_load_sources_from_admin_db() and DatabaseService._load_from_admin_db().
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_engine: Engine | None = None


def get_admin_engine() -> Engine:
    """Get or create a SQLAlchemy engine for Django's admin database.

    Requires ADMIN_DATABASE_URL environment variable.
    Raises RuntimeError if not configured.
    """
    global _engine
    if _engine is not None:
        return _engine

    db_url = os.environ.get("ADMIN_DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError(
            "ADMIN_DATABASE_URL is not set. Cannot write to Django database from the MCP server."
        )

    from sqlalchemy import create_engine

    _engine = create_engine(db_url, pool_pre_ping=True)
    logger.info("Admin DB engine created for dashboard tools")
    return _engine
