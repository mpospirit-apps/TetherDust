"""Built-in MCP seed rows must mirror the tools registered at runtime."""

from __future__ import annotations

from engine.builtin_mcp import BUILTIN_TOOLS

from ._helpers import registered_tools


def test_builtin_seed_matches_registered_tools() -> None:
    seeded = {tool_name for tool_name, *_ in BUILTIN_TOOLS}
    assert seeded == set(registered_tools())
