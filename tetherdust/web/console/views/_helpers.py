"""Shared helpers and logger used across admin_views submodules."""

import datetime
import decimal
import json
import logging
import os
from pathlib import Path

from core.models import SystemConfiguration
from django.conf import settings

logger = logging.getLogger("console.views")


def _serialize_sql_value(val: object) -> object:
    """Convert non-JSON-serializable SQL result values to strings."""
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, datetime.timedelta):
        return val.total_seconds()
    return val


def _get_docgen_timeout() -> float:
    val = SystemConfiguration.get_value("docgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("DOCGEN_TIMEOUT", "1800"))


def _get_doclibgen_timeout() -> float:
    """Timeout for AI library generation (longer than single-file docgen)."""
    val = SystemConfiguration.get_value("doclibgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("DOCLIBGEN_TIMEOUT", "3600"))


def _get_chartgen_timeout() -> float:
    val = SystemConfiguration.get_value("chartgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("CHARTGEN_TIMEOUT", "1800"))


def _get_documentation_folder_choices() -> list[tuple[str, str]]:
    """Discover subfolders inside the documentations/ directory for dropdown."""
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
    choices = [("", "— Select a folder —")]
    if docs_dir.exists() and docs_dir.is_dir():
        for entry in sorted(docs_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                choices.append((entry.name, entry.name))
    return choices


def _parse_docgen_result(result_text: str) -> list[dict]:
    """Best-effort extraction of structured errors from MCP tool return."""
    errors: list[dict] = []
    for line in result_text.splitlines():
        line = line.strip()
        if line.startswith("- Errors:"):
            try:
                errors = json.loads(line[len("- Errors:") :].strip())
            except (json.JSONDecodeError, ValueError):
                pass
    return errors


# Documentation-generation prompts moved to ``core.prompts.docs`` (Phase 1 prompt
# consolidation). Imported there by ``console/views/docsource.py``.
