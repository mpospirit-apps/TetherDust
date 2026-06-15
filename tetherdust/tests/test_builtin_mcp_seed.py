"""Built-in MCP seed rows must mirror the tools registered at runtime."""

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp_server.tools import register_tools

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from core.builtin_mcp import BUILTIN_TOOLS  # noqa: E402


def test_builtin_seed_matches_registered_tools() -> None:
    mcp = FastMCP("test")
    register_tools(mcp)

    registered = set(mcp._tool_manager._tools)
    seeded = {tool_name for tool_name, *_ in BUILTIN_TOOLS}

    assert seeded == registered
