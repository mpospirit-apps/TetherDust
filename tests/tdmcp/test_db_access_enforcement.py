"""Database access control is enforced centrally, not by convention.

The risk these guard against: a new data-touching tool that accepts a
``database`` argument but forgets to check the per-request allowed-database set
would *fail open* (silently query a database the role may not access).

The structural test makes that omission a CI failure; the functional tests
assert the shared ``@enforce_db_access`` decorator actually rejects a disallowed
database before the tool body runs.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from tdmcp.tools._db_shared import DB_ACCESS_ATTR, check_database_access, enforce_db_access

from ._helpers import registered_tools


def _has_database_param(fn: Callable[..., object]) -> bool:
    return "database" in inspect.signature(fn).parameters


# ── The shared primitive ──────────────────────────────────────────────────────


def test_unfiltered_allows_everything(set_allowed_databases: Any) -> None:
    # No filter registered (stdio use): contextvar default is None → allow all.
    set_allowed_databases(None)
    assert check_database_access("anything") is None


def test_enforces_whitelist(set_allowed_databases: Any) -> None:
    set_allowed_databases({"allowed_db"})
    assert check_database_access("allowed_db") is None
    denied = check_database_access("forbidden_db")
    assert denied is not None and "forbidden_db" in denied


def test_unnamed_resolves_default_and_denies(
    stub_db_service: Any, set_allowed_databases: Any
) -> None:
    """Omitting the database must not bypass the filter: the resolved default
    ("forbidden_db") is outside the role, so it must be denied."""
    stub_db_service(["forbidden_db", "allowed_db"])
    set_allowed_databases({"allowed_db"})
    denied = check_database_access(None)
    assert denied is not None and "forbidden_db" in denied


def test_unnamed_allows_when_default_permitted(
    stub_db_service: Any, set_allowed_databases: Any
) -> None:
    stub_db_service(["allowed_db", "other_db"])
    set_allowed_databases({"allowed_db"})
    assert check_database_access(None) is None


def test_unnamed_allows_when_nothing_configured(
    stub_db_service: Any, set_allowed_databases: Any
) -> None:
    # No databases configured → no default to resolve, nothing to deny.
    stub_db_service([])
    set_allowed_databases({"allowed_db"})
    assert check_database_access(None) is None


# ── The decorator ──────────────────────────────────────────────────────────────


async def test_enforce_db_access_short_circuits_before_body(set_allowed_databases: Any) -> None:
    ran = False

    @enforce_db_access()
    async def tool(database: str | None = None) -> str:
        nonlocal ran
        ran = True
        return "executed"

    set_allowed_databases({"allowed_db"})

    result = await tool(database="forbidden_db")
    assert "forbidden_db" in result
    assert not ran  # body must not run on denial

    assert await tool(database="allowed_db") == "executed"
    assert ran


def test_enforce_db_access_sets_marker() -> None:
    @enforce_db_access(arg="db_name")
    async def tool(db_name: str | None = None) -> str:
        return "ok"

    assert getattr(tool, DB_ACCESS_ATTR) == "db_name"


# ── The guarantee across all registered tools ──────────────────────────────────


def test_every_database_tool_opts_into_enforcement() -> None:
    """Any registered tool with a ``database`` arg MUST carry the enforcement marker.

    The fails-closed guarantee: adding a database tool without
    ``@enforce_db_access`` breaks this test instead of shipping an open hole.
    """
    offenders = [
        name
        for name, fn in registered_tools().items()
        if _has_database_param(fn) and getattr(fn, DB_ACCESS_ATTR, None) != "database"
    ]
    assert not offenders, (
        f"These tools take a `database` argument but do not enforce access via "
        f"@enforce_db_access: {offenders}"
    )


@pytest.mark.parametrize(
    "name,fn",
    sorted(
        ((n, f) for n, f in registered_tools().items() if getattr(f, DB_ACCESS_ATTR, None)),
        key=lambda item: item[0],
    ),
)
async def test_database_tool_rejects_disallowed_database(
    name: str, fn: Any, set_allowed_databases: Any
) -> None:
    """Every enforcing tool rejects a disallowed database with a denial message."""
    set_allowed_databases({"allowed_db"})
    arg = getattr(fn, DB_ACCESS_ATTR)
    # The decorator checks access before invoking the body, so every other
    # (required) argument can be omitted — the body is never reached.
    result = await fn(**{arg: "forbidden_db"})
    assert isinstance(result, str)
    assert "forbidden_db" in result
    assert "not available for your role" in result
