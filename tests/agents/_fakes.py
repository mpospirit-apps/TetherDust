"""Reusable test doubles for the Direct API agent.

Importable helpers (classes + builders) live here; the fixtures that wire them
into a test (``fake_session``, ``patch_mcp``) live in ``conftest.py``. Keeping
the fakes import-friendly lets tests that need a bespoke variant (e.g. a
capturing ``stream``) build on ``make_fake_client`` directly.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from types import SimpleNamespace
from typing import Any


class FakeConfig:
    """Duck-typed stand-in for ``AgentConfiguration``."""

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.test/v1",
        api_key: str = "sk-test",
    ) -> None:
        self.system_prompt = "You are a test agent."
        self.settings = {"model": model, "base_url": base_url}
        self.api_key = api_key


class FakeSession:
    """Minimal MCP ``ClientSession``: one tool, records ``call_tool`` invocations."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def list_tools(self) -> Any:
        tool = SimpleNamespace(
            name="list_tables",
            description="List tables",
            inputSchema={"type": "object", "properties": {"database": {"type": "string"}}},
        )
        return SimpleNamespace(tools=[tool])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text="users, orders")])


class FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code
        self.request = SimpleNamespace()
        self.closed = False

    async def __aenter__(self) -> FakeStreamResponse:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def aiter_lines(self) -> AsyncGenerator[str, None]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b'{"error": "boom"}'

    async def aclose(self) -> None:
        self.closed = True


def make_fake_client(rounds: list[list[str]], raise_exc: BaseException | None = None) -> type[Any]:
    """Build a fake ``httpx.AsyncClient`` class that replays ``rounds`` of SSE lines."""
    queue = list(rounds)

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        def stream(
            self,
            method: str,
            url: str,
            json: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> FakeStreamResponse:
            if raise_exc is not None:
                raise raise_exc
            return FakeStreamResponse(queue.pop(0))

        # The agent always registers (POST) a per-request MCP filter token and
        # clears it (DELETE) afterwards, before/after the provider stream. These
        # succeed regardless of ``raise_exc``, which targets the provider stream
        # only — so transport-error tests still exercise the stream path.
        async def post(
            self,
            url: str,
            json: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> Any:
            return SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"status": "registered"},
            )

        async def delete(self, url: str, headers: dict[str, str] | None = None) -> Any:
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    return FakeAsyncClient


def sse(*objs: dict[str, Any]) -> list[str]:
    """Render dicts as provider SSE ``data:`` lines, terminated by ``[DONE]``."""
    return [f"data: {json.dumps(o)}" for o in objs] + ["data: [DONE]"]


async def collect(agen: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in agen]
