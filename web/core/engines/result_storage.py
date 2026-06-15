"""Filesystem-based storage for report execution results.

Results are stored as two files per execution:
- meta.json: column names and row count
- data.jsonl: one JSON array per line (preserves types)
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, cast

from django.conf import settings

logger = logging.getLogger(__name__)


def _results_dir() -> Path:
    default = settings.BASE_DIR / "report_results"
    return Path(cast("str | Path", getattr(settings, "TETHERDUST_REPORT_RESULTS_DIR", default)))


def _execution_dir(execution_id: int) -> Path:
    return _results_dir() / str(execution_id)


def save_results(execution_id: int, column_names: list[str], rows: list[list[object]]) -> None:
    """Write meta.json + data.jsonl for an execution."""
    path = _execution_dir(execution_id)
    path.mkdir(parents=True, exist_ok=True)

    meta = {"column_names": column_names, "row_count": len(rows)}
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    with (path / "data.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def load_meta(execution_id: int) -> dict[str, Any] | None:
    """Read column_names and row_count. Returns None if not found."""
    meta_path = _execution_dir(execution_id) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return cast(dict[str, Any], json.loads(meta_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read meta for execution %s: %s", execution_id, e)
        return None


def load_rows(execution_id: int, limit: int | None = None) -> list[list[object]]:
    """Read rows from data.jsonl. Optionally read only first N lines."""
    data_path = _execution_dir(execution_id) / "data.jsonl"
    if not data_path.exists():
        return []
    rows = []
    try:
        with data_path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if limit is not None and i >= limit:
                    break
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read data for execution %s: %s", execution_id, e)
    return rows


def load_all(execution_id: int) -> tuple[list[str], list[list[object]]]:
    """Read column_names + all rows. Returns ([], []) if not found."""
    meta = load_meta(execution_id)
    if not meta:
        return [], []
    return meta["column_names"], load_rows(execution_id)


def delete_results(execution_id: int) -> None:
    """Remove the result directory for an execution."""
    path = _execution_dir(execution_id)
    if path.exists():
        shutil.rmtree(path)
