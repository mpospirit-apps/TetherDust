"""Built-in MCP seed rows must mirror the tools registered at runtime."""

from __future__ import annotations

import pytest
from engine.builtin_mcp import ensure_builtin_mcp, iter_builtin_tools
from engine.models import ToolConfiguration

from ._helpers import registered_tools


def test_builtin_seed_matches_registered_tools() -> None:
    seeded = {tool_name for tool_name, *_ in iter_builtin_tools()}
    assert seeded == set(registered_tools())


@pytest.mark.django_db
def test_ensure_builtin_mcp_prunes_tools_removed_from_tdmcp(mocker) -> None:
    """A tool removed from tdmcp must not leave a stale, unremovable row —
    the built-in server's tools have no admin-editable fields, so there's
    nothing to preserve by keeping it around."""
    ensure_builtin_mcp()
    assert ToolConfiguration.objects.filter(tool_name="list_tethers").exists()

    without_list_tethers = [row for row in iter_builtin_tools() if row[0] != "list_tethers"]
    mocker.patch("engine.builtin_mcp.iter_builtin_tools", return_value=without_list_tethers)
    ensure_builtin_mcp()

    assert not ToolConfiguration.objects.filter(tool_name="list_tethers").exists()
    assert ToolConfiguration.objects.filter(mcp_server__is_builtin=True).count() == len(
        without_list_tethers
    )
