"""Tests that database access control is enforced centrally, not by convention.

The risk these guard against: a new data-touching tool that accepts a
``database`` argument but forgets to check the per-request allowed-database set
would *fail open* (silently query a database the role may not access).

The structural test makes that omission a CI failure; the functional test
asserts the shared ``@enforce_db_access`` decorator actually rejects a
disallowed database before the tool body runs.
"""

import inspect
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_server._context import request_allowed_databases
from mcp_server.tools import _db_shared, register_tools
from mcp_server.tools._db_shared import (
    DB_ACCESS_ATTR,
    check_database_access,
    enforce_db_access,
)


def _stub_db_service(monkeypatch, names):
    """Make get_db_service() report *names* as the configured connections.

    list_databases()[0] is the default execute_query() falls back to when no
    database is named, so the first entry is the one an unnamed call resolves to.
    """
    stub = SimpleNamespace(list_databases=lambda: [SimpleNamespace(name=n) for n in names])
    monkeypatch.setattr(_db_shared, "get_db_service", lambda: stub)


def _registered_tool_fns() -> dict[str, object]:
    """Return {tool_name: underlying_function} for every registered MCP tool."""
    mcp = FastMCP("test")
    register_tools(mcp)
    return {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}


def _has_database_param(fn: object) -> bool:
    """True if the tool's (signature-following) parameters include `database`."""
    return "database" in inspect.signature(fn).parameters  # type: ignore[arg-type]


# ── The shared primitive ──────────────────────────────────────────────────────


def test_check_database_access_unfiltered_allows_everything():
    # No filter registered (stdio use): contextvar default is None → allow all.
    token = request_allowed_databases.set(None)
    try:
        assert check_database_access("anything") is None
    finally:
        request_allowed_databases.reset(token)


def test_check_database_access_enforces_whitelist():
    token = request_allowed_databases.set({"allowed_db"})
    try:
        assert check_database_access("allowed_db") is None
        denied = check_database_access("forbidden_db")
        assert denied is not None
        assert "forbidden_db" in denied
    finally:
        request_allowed_databases.reset(token)


def test_check_database_access_unnamed_resolves_default_and_denies(monkeypatch):
    """Omitting the database must not bypass the filter.

    The regression: an unnamed call fell through to execute_query()'s
    first-configured-database fallback without an access check. Here the default
    ("forbidden_db") is outside the role, so it must be denied.
    """
    _stub_db_service(monkeypatch, ["forbidden_db", "allowed_db"])
    token = request_allowed_databases.set({"allowed_db"})
    try:
        denied = check_database_access(None)
        assert denied is not None
        assert "forbidden_db" in denied
    finally:
        request_allowed_databases.reset(token)


def test_check_database_access_unnamed_allows_when_default_permitted(monkeypatch):
    # Default connection is in the role's allow-list → unnamed call is fine.
    _stub_db_service(monkeypatch, ["allowed_db", "other_db"])
    token = request_allowed_databases.set({"allowed_db"})
    try:
        assert check_database_access(None) is None
    finally:
        request_allowed_databases.reset(token)


def test_check_database_access_unnamed_allows_when_nothing_configured(monkeypatch):
    # No databases configured → no default to resolve, nothing to deny.
    _stub_db_service(monkeypatch, [])
    token = request_allowed_databases.set({"allowed_db"})
    try:
        assert check_database_access(None) is None
    finally:
        request_allowed_databases.reset(token)


# ── The decorator ──────────────────────────────────────────────────────────────


async def test_enforce_db_access_short_circuits_before_body():
    ran = False

    @enforce_db_access()
    async def tool(database: str | None = None) -> str:
        nonlocal ran
        ran = True
        return "executed"

    token = request_allowed_databases.set({"allowed_db"})
    try:
        result = await tool(database="forbidden_db")
        assert "forbidden_db" in result
        assert ran is False  # body must not run on denial

        ran = False
        assert await tool(database="allowed_db") == "executed"
        assert ran is True
    finally:
        request_allowed_databases.reset(token)


def test_enforce_db_access_sets_marker():
    @enforce_db_access(arg="db_name")
    async def tool(db_name: str | None = None) -> str:
        return "ok"

    assert getattr(tool, DB_ACCESS_ATTR) == "db_name"


# ── The guarantee across all registered tools ──────────────────────────────────


def test_every_database_tool_opts_into_enforcement():
    """Any registered tool with a `database` arg MUST carry the enforcement marker.

    This is the fails-closed guarantee: adding a new database tool without
    @enforce_db_access breaks this test instead of shipping an open hole.
    """
    offenders = [
        name
        for name, fn in _registered_tool_fns().items()
        if _has_database_param(fn) and getattr(fn, DB_ACCESS_ATTR, None) != "database"
    ]
    assert not offenders, (
        f"These tools take a `database` argument but do not enforce access via "
        f"@enforce_db_access: {offenders}"
    )


@pytest.mark.parametrize(
    "name, fn",
    [(n, f) for n, f in _registered_tool_fns().items() if getattr(f, DB_ACCESS_ATTR, None)],
)
async def test_database_tool_rejects_disallowed_database(name, fn):
    """Every enforcing tool rejects a disallowed database with a denial message."""
    arg = getattr(fn, DB_ACCESS_ATTR)
    token = request_allowed_databases.set({"allowed_db"})
    try:
        # The decorator checks access before invoking the body, so we can omit
        # every other (required) argument — the body is never reached.
        result = await fn(**{arg: "forbidden_db"})
    finally:
        request_allowed_databases.reset(token)
    assert isinstance(result, str)
    assert "forbidden_db" in result
    assert "not available for your role" in result
