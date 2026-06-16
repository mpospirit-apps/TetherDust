"""Shared helpers and logger used across admin_views submodules."""

import datetime
import decimal
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from engine.models import SystemConfiguration

logger = logging.getLogger("management.views")

_V = TypeVar("_V", bound=Callable[..., Any])


def staff_required(view: _V) -> _V:
    """Typed wrapper for staff_member_required(login_url='/login/').

    The bare @staff_member_required(login_url=...) call matches the untyped
    overload in django-stubs, making every decorated function untyped. By
    passing view_func positionally, we hit the typed overload that preserves _V.
    """
    return staff_member_required(view, login_url="/login/")


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


def _parse_docgen_result(result_text: str) -> list[dict[str, object]]:
    """Best-effort extraction of structured errors from MCP tool return."""
    errors: list[dict[str, object]] = []
    for line in result_text.splitlines():
        line = line.strip()
        if line.startswith("- Errors:"):
            try:
                errors = json.loads(line[len("- Errors:") :].strip())
            except (json.JSONDecodeError, ValueError):
                pass
    return errors


# Documentation-generation prompts moved to ``engine.prompts.docs`` (Phase 1 prompt
# consolidation). Imported there by ``management/views/docsource.py``.
