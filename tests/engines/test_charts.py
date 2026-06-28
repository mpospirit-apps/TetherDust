"""charts: value serialization, cached chart data, and ad-hoc preview."""

from __future__ import annotations

import datetime
import decimal
from typing import Any

import pytest
from engine.engines import charts
from engine.models import DatabaseConnection
from model_bakery import baker

# --- serialize_sql_value (pure) ---------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (datetime.datetime(2026, 1, 2, 3, 4, 5), "2026-01-02T03:04:05"),
        (datetime.date(2026, 1, 2), "2026-01-02"),
        (datetime.time(3, 4, 5), "03:04:05"),
        (decimal.Decimal("9.50"), 9.5),
        (datetime.timedelta(seconds=90), 90.0),
        ("plain", "plain"),
        (42, 42),
        (None, None),
    ],
)
def test_serialize_sql_value(value: object, expected: object) -> None:
    assert charts.serialize_sql_value(value) == expected


# --- chart_data (DB-backed; db_runner mocked) -------------------------------


@pytest.mark.django_db
def test_chart_data_runs_and_caches(mocker: Any) -> None:
    mocker.patch(
        "engine.engines.db_runner.run_query",
        return_value=(["label", "value"], [["a", 1], ["b", 2]]),
    )
    chart = baker.make("engine.Chart", cached_data={})

    result = charts.chart_data(chart)
    assert result["cached"] is False
    assert result["columns"] == ["label", "value"]
    assert result["data"] == [{"label": "a", "value": 1}, {"label": "b", "value": 2}]

    chart.refresh_from_db()
    assert chart.cached_data["rows"] == result["data"]
    assert chart.last_error == ""


@pytest.mark.django_db
def test_chart_data_serves_cache_without_requery(mocker: Any) -> None:
    run_query = mocker.patch("engine.engines.db_runner.run_query")
    chart = baker.make(
        "engine.Chart",
        cached_data={"columns": ["n"], "rows": [{"n": 1}], "refreshed_at": "2026-01-01T00:00:00"},
    )

    result = charts.chart_data(chart)
    assert result["cached"] is True
    assert result["data"] == [{"n": 1}]
    run_query.assert_not_called()


@pytest.mark.django_db
def test_chart_data_force_refresh_requeries(mocker: Any) -> None:
    run_query = mocker.patch("engine.engines.db_runner.run_query", return_value=(["n"], [[9]]))
    chart = baker.make("engine.Chart", cached_data={"columns": ["n"], "rows": [{"n": 1}]})

    result = charts.chart_data(chart, force_refresh=True)
    assert result["cached"] is False
    assert result["data"] == [{"n": 9}]
    run_query.assert_called_once()


@pytest.mark.django_db
def test_chart_data_records_error_and_reraises(mocker: Any) -> None:
    mocker.patch("engine.engines.db_runner.run_query", side_effect=RuntimeError("boom"))
    chart = baker.make("engine.Chart", cached_data={})

    with pytest.raises(RuntimeError, match="boom"):
        charts.chart_data(chart)

    chart.refresh_from_db()
    assert "boom" in chart.last_error


# --- preview_query (validation + run; no DB needed) -------------------------


def test_preview_query_runs_valid_sql(mocker: Any) -> None:
    mocker.patch("engine.engines.db_runner.run_query", return_value=(["n"], [[1]]))
    conn = DatabaseConnection(engine="postgresql")

    result = charts.preview_query(conn, "SELECT n FROM t")
    assert result == {"columns": ["n"], "data": [{"n": 1}]}


def test_preview_query_rejects_write_sql(mocker: Any) -> None:
    run_query = mocker.patch("engine.engines.db_runner.run_query")
    conn = DatabaseConnection(engine="postgresql")

    with pytest.raises(ValueError):
        charts.preview_query(conn, "DELETE FROM t")
    run_query.assert_not_called()  # rejected before execution
