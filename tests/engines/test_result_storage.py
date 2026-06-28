"""result_storage: filesystem round-trip for report results.

``TETHERDUST_REPORT_RESULTS_DIR`` is redirected to ``tmp_path`` so each test
writes into an isolated directory.
"""

from __future__ import annotations

from typing import Any

import pytest
from engine.engines import result_storage


@pytest.fixture(autouse=True)
def _isolate_results_dir(settings: Any, tmp_path: Any) -> None:
    settings.TETHERDUST_REPORT_RESULTS_DIR = str(tmp_path)


def test_round_trip_preserves_types() -> None:
    columns = ["id", "name", "amount", "active", "missing"]
    rows = [[1, "alice", 9.5, True, None], [2, "bob", 0.0, False, None]]
    result_storage.save_results("rex_1", columns, rows)

    assert result_storage.load_meta("rex_1") == {"column_names": columns, "row_count": 2}
    assert result_storage.load_rows("rex_1") == rows  # ints/floats/bools/None survive JSONL


def test_load_rows_respects_limit() -> None:
    result_storage.save_results("rex_2", ["n"], [[1], [2], [3]])
    assert result_storage.load_rows("rex_2", limit=2) == [[1], [2]]


def test_load_all_returns_columns_and_rows() -> None:
    result_storage.save_results("rex_3", ["a"], [["x"]])
    assert result_storage.load_all("rex_3") == (["a"], [["x"]])


def test_missing_execution_reads_empty() -> None:
    assert result_storage.load_meta("absent") is None
    assert result_storage.load_rows("absent") == []
    assert result_storage.load_all("absent") == ([], [])


def test_delete_removes_results() -> None:
    result_storage.save_results("rex_4", ["a"], [["x"]])
    result_storage.delete_results("rex_4")
    assert result_storage.load_meta("rex_4") is None
    # Deleting a non-existent execution is a no-op (must not raise).
    result_storage.delete_results("rex_4")
