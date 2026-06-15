"""Shared database utilities for database tools.

Provides lazy-initialized DatabaseService and per-request access controls
populated by the token-based filter middleware in ``server.py``.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from .._context import (
    request_allowed_codebases,
    request_allowed_dashboards,
    request_allowed_databases,
    request_allowed_doc_sources,
    request_allowed_reports,
    request_allowed_tethers,
    request_max_row_limit,
)
from ..utils.db_service import DatabaseService

# Marker attribute set by @enforce_db_access. A central gate / test can read it
# to discover which tools enforce database access and on which argument.
DB_ACCESS_ATTR = "__db_access_arg__"

# Global database service instance (initialized lazily)
_db_service: DatabaseService | None = None


def get_db_service() -> DatabaseService:
    """Get or create the database service."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service


def get_allowed_databases() -> set[str] | None:
    """Allowed databases from the per-request context var.

    Returns None when no filter is registered (unfiltered stdio use).
    """
    return request_allowed_databases.get(None)


def get_allowed_doc_sources() -> set[str] | None:
    """Allowed doc sources from the per-request context var."""
    return request_allowed_doc_sources.get(None)


def get_allowed_codebases() -> set[str] | None:
    """Allowed codebases from the per-request context var."""
    return request_allowed_codebases.get(None)


def get_allowed_reports() -> set[str] | None:
    """Allowed report names from the per-request context var.

    Returns None when unrestricted (staff/admin role). Returns a set of report
    names when the role has an explicit allow-list.
    """
    return request_allowed_reports.get(None)


def get_allowed_dashboards() -> set[str] | None:
    """Allowed dashboard names from the per-request context var.

    Returns None when unrestricted. Returns a set of dashboard names when the
    role has an explicit allow-list.
    """
    return request_allowed_dashboards.get(None)


def get_allowed_tethers() -> set[str] | None:
    """Allowed tether IDs (as strings) from the per-request context var.

    Returns None when unrestricted. Returns a set of tether ID strings when the
    role has an explicit allow-list.
    """
    return request_allowed_tethers.get(None)


def get_max_row_limit() -> int | None:
    """Max row limit from the per-request context var, or None if unset."""
    return request_max_row_limit.get(None)


def check_database_access(database: str | None) -> str | None:
    """Single enforcement primitive for per-request database access.

    Returns an access-denied message if *database* is outside the role's
    allowed set, or None when access is permitted (the unfiltered stdio case
    where no filter is registered, or no databases configured).

    An unnamed (None) database is *not* waved through: ``execute_query`` falls
    back to the first configured connection, so we resolve that same default and
    check it against the role. Otherwise a restricted role could read the
    first-configured database simply by omitting the ``database`` argument.
    """
    allowed = get_allowed_databases()
    if allowed is None:
        return None  # no filter registered (stdio) — allow all

    if not database:
        # Mirror execute_query()'s default-database fallback (the first
        # configured connection) so the access check covers it too.
        configs = get_db_service().list_databases()
        if not configs:
            return None  # nothing configured — nothing to deny
        database = configs[0].name

    if database not in allowed:
        return f"Access denied: database '{database}' is not available for your role."
    return None


_F = TypeVar("_F", bound=Callable[..., Awaitable[str]])


def enforce_db_access(*, arg: str = "database") -> Callable[[_F], _F]:
    """Decorator that gates a tool on database access before it runs.

    The wrapped tool's *arg* keyword (default ``"database"``) is checked against
    the per-request allowed-database set; a disallowed value short-circuits with
    the standard denial message so the tool body never touches the database.

    Applying this decorator is the easy, safe path: it makes database
    enforcement declarative instead of a per-tool convention that a new tool
    can silently forget. The marker attribute it sets lets a test assert that
    every database-touching tool opts in (see tests/test_db_access_enforcement.py).
    """

    def decorator(func: _F) -> _F:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> str:
            db_arg = kwargs.get(arg)
            denied = check_database_access(db_arg if isinstance(db_arg, str) else None)
            if denied is not None:
                return denied
            return await func(*args, **kwargs)

        setattr(wrapper, DB_ACCESS_ATTR, arg)
        return cast(_F, wrapper)

    return decorator
