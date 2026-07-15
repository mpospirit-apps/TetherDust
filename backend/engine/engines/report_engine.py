"""Report execution engine for TetherDust.

Executes SQL reports against configured databases and stores results.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import TYPE_CHECKING

import sqlglot
from django.contrib.auth.models import User
from django.utils import timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import expressions as exp

from .db_runner import run_query

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models import ReportDefinition, ReportExecution

# Statement node types that mutate data/schema or run procedural code.
# Mirrors mcp_server/utils/db_service.py — keep in sync.
_FORBIDDEN_NODES = tuple(
    t
    for t in (
        getattr(exp, name, None)
        for name in (
            "Insert",
            "Update",
            "Delete",
            "Merge",
            "Drop",
            "Create",
            "Alter",
            "TruncateTable",
            "Command",
            "Set",
            "Grant",
            "Copy",
            "Into",
        )
    )
    if t is not None
)

_ALLOWED_ROOTS = tuple(
    t
    for t in (
        getattr(exp, name, None)
        for name in ("Select", "Union", "Except", "Intersect", "SetOperation", "Subquery", "Paren")
    )
    if t is not None
)

# Engine name → sqlglot dialect (subset used by reports).
_SQLGLOT_DIALECTS = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "sqlite": "sqlite",
    "clickhouse": "clickhouse",
}


def validate_sql(sql: str, engine: str | None = None) -> str | None:
    """Validate that ``sql`` is a single read-only SELECT/CTE/set-operation.

    Uses sqlglot AST parsing (dialect-aware) and fails closed on unparseable
    input. Returns an error message string if invalid, None if valid.
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "SQL query cannot be empty."

    dialect = _SQLGLOT_DIALECTS.get(engine or "")
    try:
        statements = [s for s in sqlglot.parse(stripped, dialect=dialect) if s is not None]
    except Exception as err:
        return f"Query could not be parsed as valid SQL: {err}"

    if not statements:
        return "SQL query cannot be empty."
    if len(statements) > 1:
        return "Only a single SELECT statement is allowed."

    root = statements[0]
    if not isinstance(root, _ALLOWED_ROOTS):
        return (
            "Only read-only SELECT queries are allowed (the statement must be a "
            "SELECT, CTE, or set operation)."
        )
    has_forbidden = (
        isinstance(root, _FORBIDDEN_NODES)
        or next(root.find_all(*_FORBIDDEN_NODES), None) is not None
    )
    if has_forbidden:
        return (
            "Query contains a write or procedural statement. "
            "Only read-only SELECT queries are allowed."
        )

    return None


def execute_report(
    report_definition: ReportDefinition,
    triggered_by: User | None = None,
    max_rows_override: int | None = None,
) -> ReportExecution:
    """Execute a report definition and store results.

    Args:
        report_definition: ReportDefinition instance
        triggered_by: User who triggered the run (None for scheduled)
        max_rows_override: Override max_rows (used for preview, e.g. 10 rows)

    Returns:
        ReportExecution instance
    """
    from ..models import ReportExecution

    execution = ReportExecution.objects.create(
        definition=report_definition,
        status="running",
        triggered_by=triggered_by,
    )

    sql = report_definition.sql_query.strip().rstrip(";")

    # Validate SQL (pass engine for dialect-aware AST parsing)
    error = validate_sql(sql, engine=report_definition.database.engine)
    if error:
        execution.status = "failed"
        execution.error_message = error
        execution.completed_at = timezone.now()
        execution.save()
        return execution

    db = report_definition.database

    # Apply LIMIT only for admin preview (max_rows_override)
    if max_rows_override:
        sql = f"SELECT * FROM ({sql}) AS _td_report LIMIT {max_rows_override}"

    start_time = time.monotonic()

    try:
        columns, rows = run_query(db, sql)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Convert non-serializable values to strings
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                if val is not None and not isinstance(val, (str, int, float, bool)):
                    rows[i][j] = str(val)

        from .result_storage import save_results

        save_results(execution.pk, columns, rows)
        execution.status = "success"
        execution.result_file_path = str(execution.pk)
        execution.row_count = len(rows)
        execution.execution_time_ms = elapsed_ms
        execution.completed_at = timezone.now()
        execution.save()

    except (SQLAlchemyError, Exception) as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        execution.status = "failed"
        execution.error_message = str(e)
        execution.execution_time_ms = elapsed_ms
        execution.completed_at = timezone.now()
        execution.save()
        logger.error("Report execution failed: %s — %s", report_definition.name, e)

    # Compute next_run_at for scheduled reports
    if report_definition.schedule_type != "manual":
        report_definition.next_run_at = compute_next_run(report_definition)
        report_definition.save(update_fields=["next_run_at"])

    return execution


def compute_next_run(report_definition: ReportDefinition) -> datetime | None:
    """Compute the next scheduled run time for a report."""
    now = timezone.now()
    schedule_type = report_definition.schedule_type
    run_time = report_definition.schedule_time or dt_time(0, 0)

    if schedule_type == "interval":
        minutes = report_definition.schedule_interval_minutes or 60
        return now + timedelta(minutes=minutes)

    elif schedule_type == "daily":
        next_dt = now.replace(hour=run_time.hour, minute=run_time.minute, second=0, microsecond=0)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        return next_dt

    elif schedule_type == "weekly":
        day_of_week = report_definition.schedule_day_of_week or 0
        next_dt = now.replace(hour=run_time.hour, minute=run_time.minute, second=0, microsecond=0)
        days_ahead = day_of_week - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and next_dt <= now):
            days_ahead += 7
        next_dt += timedelta(days=days_ahead)
        return next_dt

    elif schedule_type == "monthly":
        day_of_month = report_definition.schedule_day_of_month or 1
        next_dt = now.replace(
            day=min(day_of_month, 28),
            hour=run_time.hour,
            minute=run_time.minute,
            second=0,
            microsecond=0,
        )
        if next_dt <= now:
            # Move to next month
            if now.month == 12:
                next_dt = next_dt.replace(year=now.year + 1, month=1)
            else:
                next_dt = next_dt.replace(month=now.month + 1)
        return next_dt

    return None
