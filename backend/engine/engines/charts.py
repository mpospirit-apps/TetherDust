"""Chart data execution + ad-hoc preview helpers.

Shared by the public chart-data endpoint and the admin chart editor (ports the
duplicated bodies of ``workspace/views/dashboards.py`` + ``management/views/
dashboard.py``). Read-only SQL is validated via ``report_engine.validate_sql``
before execution; chart results are cached back onto the row on refresh.
"""

from __future__ import annotations

import datetime
import decimal
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from engine.models import Chart, DatabaseConnection


def serialize_sql_value(val: object) -> object:
    """Convert non-JSON-serializable SQL result values to JSON-friendly ones."""
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, datetime.timedelta):
        return val.total_seconds()
    return val


def _rows_as_dicts(columns: list[str], raw_rows: list[Any]) -> list[dict[str, Any]]:
    return [{col: serialize_sql_value(v) for col, v in zip(columns, row)} for row in raw_rows]


def chart_data(chart: Chart, force_refresh: bool = False) -> dict[str, Any]:
    """Return ``{columns, data, cached, refreshed_at}`` for a chart.

    Uses cached data unless ``force_refresh``. On a fresh run the result is
    cached back onto the chart. Raises on query failure (after recording
    ``last_error``); callers surface a 500.
    """
    from engine.engines.db_runner import run_query

    if not force_refresh and chart.cached_data and chart.cached_data.get("rows"):
        return {
            "columns": chart.cached_data.get("columns", []),
            "data": chart.cached_data.get("rows", []),
            "cached": True,
            "refreshed_at": chart.cached_data.get("refreshed_at"),
        }

    try:
        columns, raw_rows = run_query(chart.database, chart.sql_query)
        rows = _rows_as_dicts(columns, raw_rows)
        now_str = timezone.now().isoformat()
        chart.cached_data = {"columns": columns, "rows": rows, "refreshed_at": now_str}
        chart.last_refreshed_at = timezone.now()
        chart.last_error = ""
        chart.save(update_fields=["cached_data", "last_refreshed_at", "last_error"])
        return {"columns": columns, "data": rows, "cached": False, "refreshed_at": now_str}
    except Exception as exc:
        chart.last_error = str(exc)
        chart.save(update_fields=["last_error"])
        raise


def preview_query(db_conn: DatabaseConnection, sql: str) -> dict[str, Any]:
    """Validate + run an ad-hoc read-only query for the editor preview.

    Returns ``{columns, data}``. Raises ``ValueError`` if the SQL fails
    read-only validation; other exceptions propagate from execution.
    """
    from engine.engines.db_runner import run_query
    from engine.engines.report_engine import validate_sql

    error = validate_sql(sql, engine=db_conn.engine)
    if error:
        raise ValueError(error)
    columns, raw_rows = run_query(db_conn, sql)
    return {"columns": columns, "data": _rows_as_dicts(columns, raw_rows)}
