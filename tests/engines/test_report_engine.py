"""report_engine: read-only SQL validation and schedule arithmetic.

``validate_sql`` and the tdmcp ``validate_read_only_sql`` are two copies of the
same AST-based guard that "must be kept in sync"; the parity test pins that.
"""

from __future__ import annotations

import datetime

import pytest
from engine.engines.report_engine import compute_next_run, validate_sql
from engine.models import ReportDefinition
from freezegun import freeze_time

from tdmcp.utils.db_service import QueryValidationError, validate_read_only_sql

# (sql, is_allowed) corpus shared by the validator tests and the parity check.
_CASES = [
    ("SELECT 1", True),
    ("SELECT * FROM users", True),
    ("select id, name from users where id > 1", True),
    ("WITH x AS (SELECT 1 AS n) SELECT n FROM x", True),
    ("SELECT a FROM t UNION SELECT b FROM u", True),
    ("(SELECT 1)", True),
    ("SELECT 1;", True),  # trailing semicolon tolerated
    ("", False),
    ("   ", False),
    ("INSERT INTO t (a) VALUES (1)", False),
    ("UPDATE t SET a = 1", False),
    ("DELETE FROM t", False),
    ("DROP TABLE t", False),
    ("CREATE TABLE t (a int)", False),
    ("ALTER TABLE t ADD COLUMN c int", False),
    ("TRUNCATE TABLE t", False),
    ("GRANT SELECT ON t TO u", False),
    ("SELECT 1; SELECT 2", False),  # multiple statements
    ("SELECT * FROM (DELETE FROM t)", False),  # write nested in a subquery
    ("this is not sql", False),
]


@pytest.mark.parametrize("sql,allowed", _CASES, ids=[c[0][:24] or "blank" for c in _CASES])
def test_validate_sql(sql: str, allowed: bool) -> None:
    result = validate_sql(sql)
    assert (result is None) is allowed
    if not allowed:
        assert isinstance(result, str) and result  # a non-empty error message


@pytest.mark.parametrize("sql,allowed", _CASES, ids=[c[0][:24] or "blank" for c in _CASES])
def test_validator_parity_with_tdmcp(sql: str, allowed: bool) -> None:
    """report_engine.validate_sql and tdmcp.validate_read_only_sql must agree."""
    report_ok = validate_sql(sql) is None
    try:
        validate_read_only_sql(sql)
        tdmcp_ok = True
    except QueryValidationError:
        tdmcp_ok = False
    assert report_ok == tdmcp_ok == allowed


def test_validate_sql_dialect_specific_select() -> None:
    # A dialect hint is accepted and a plain SELECT stays valid across dialects.
    for engine in ("postgresql", "mysql", "mssql", "clickhouse", "bigquery"):
        assert validate_sql("SELECT 1", engine=engine) is None


# --- compute_next_run --------------------------------------------------------


def test_compute_next_run_interval() -> None:
    definition = ReportDefinition(schedule_type="interval", schedule_interval_minutes=30)
    with freeze_time("2026-06-01T12:00:00Z"):
        result = compute_next_run(definition)
    assert result == datetime.datetime(2026, 6, 1, 12, 30, tzinfo=datetime.UTC)


def test_compute_next_run_daily_rolls_to_tomorrow_when_past() -> None:
    definition = ReportDefinition(schedule_type="daily", schedule_time=datetime.time(9, 0))
    with freeze_time("2026-06-01T12:00:00Z"):  # 09:00 already passed today
        result = compute_next_run(definition)
    assert result == datetime.datetime(2026, 6, 2, 9, 0, tzinfo=datetime.UTC)


def test_compute_next_run_manual_is_none() -> None:
    assert compute_next_run(ReportDefinition(schedule_type="manual")) is None
