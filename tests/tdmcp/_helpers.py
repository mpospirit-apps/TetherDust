"""Shared, importable helpers for tdmcp tool tests.

The MCP registry is identical for every test, so build it once and cache it —
both the access-enforcement parametrization (evaluated at collection time) and
the built-in-seed test read from here.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from tdmcp.tools import register_tools


@functools.lru_cache(maxsize=1)
def registered_tools() -> dict[str, Callable[..., object]]:
    """Map every registered MCP tool name to its underlying function (cached)."""
    mcp = FastMCP("test")
    register_tools(mcp)
    return {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}
