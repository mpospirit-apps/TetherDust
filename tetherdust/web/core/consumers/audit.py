"""Audit-log helpers for the chat WebSocket consumers."""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


@database_sync_to_async
def log_queries_from_response(user, response: str) -> None:
    """Parse agent response for query indicators and create an audit log entry."""
    from ..models import QueryAuditLog

    if "Query Results" not in response and "Query execution error" not in response:
        return

    try:
        success = "Query Results" in response
        QueryAuditLog.objects.create(
            user=user,
            database=None,
            query="[extracted from agent response]",
            row_count=None,
            execution_time_ms=None,
            success=success,
            error_message="" if success else "Query error detected in agent response",
        )
    except Exception:
        logger.exception("Failed to create audit log entry")
