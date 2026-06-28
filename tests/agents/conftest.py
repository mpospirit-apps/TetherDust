"""Fixtures for the Direct API agent tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import pytest

from ._fakes import FakeSession


@pytest.fixture
def fake_session() -> FakeSession:
    """A fresh MCP session double recording its ``call_tool`` invocations."""
    return FakeSession()


@pytest.fixture
def patch_mcp(monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeSession], None]:
    """Patch ``open_mcp_session`` so the agent talks to the given fake session."""
    from engine.agents import direct_api

    def _patch(session: FakeSession) -> None:
        @asynccontextmanager
        async def fake_open(
            url: str, headers: dict[str, str] | None = None
        ) -> AsyncGenerator[FakeSession, None]:
            yield session

        monkeypatch.setattr(direct_api, "open_mcp_session", fake_open)

    return _patch
