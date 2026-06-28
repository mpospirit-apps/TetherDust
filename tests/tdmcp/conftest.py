"""Fixtures for tdmcp tool tests.

These wrap the two pieces of per-request state the tools read from contextvars
(the allowed-database set and the filter token) plus the server's global
tool-call buffers, so individual tests stay free of ``set``/``try``/``reset``
boilerplate and don't leak state into one another.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _clear_tool_call_buffers() -> Iterator[None]:
    """Isolate the server's global per-token tool-call buffers between tests."""
    from tdmcp import server

    server._tool_calls_by_token.clear()
    yield
    server._tool_calls_by_token.clear()


@pytest.fixture
def set_allowed_databases() -> Iterator[Callable[[set[str] | None], None]]:
    """Set the per-request allowed-database contextvar; clear it after the test.

    Teardown uses ``set(None)`` (the var's default) rather than ``Token.reset``:
    async tests set the var inside the coroutine's copied context, where the
    token cannot be reset from the synchronous teardown context.
    """
    from tdmcp._context import request_allowed_databases

    def _set(value: set[str] | None) -> None:
        request_allowed_databases.set(value)

    yield _set
    request_allowed_databases.set(None)


@pytest.fixture
def stub_db_service(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[str]], None]:
    """Make ``get_db_service().list_databases()`` report the given connection names.

    ``list_databases()[0]`` is the default an unnamed query resolves to, so the
    first name is what an access check sees when ``database`` is omitted.
    """
    from tdmcp.tools import _db_shared

    def _stub(names: list[str]) -> None:
        svc = SimpleNamespace(list_databases=lambda: [SimpleNamespace(name=n) for n in names])
        monkeypatch.setattr(_db_shared, "get_db_service", lambda: svc)

    return _stub


@pytest.fixture
def record_tool_calls() -> Callable[..., None]:
    """Record tool calls under a filter token, handling the contextvar set/reset."""
    from tdmcp import server
    from tdmcp._context import request_filter_token

    def _record(token: str, *names: str) -> None:
        tok = request_filter_token.set(token)
        try:
            for name in names:
                server._record_tool_call(name)
        finally:
            request_filter_token.reset(tok)

    return _record
