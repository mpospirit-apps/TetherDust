"""McpServerService / ToolService — small classification helpers (no DB needed)."""

from __future__ import annotations

from engine.models import MCPServerConfiguration, ToolConfiguration
from engine.services import McpServerService, ToolService, get


def test_is_local_true_for_command_non_builtin() -> None:
    server = MCPServerConfiguration(command="run.sh", is_builtin=False)
    assert get(McpServerService).is_local(server) is True


def test_is_local_false_for_builtin() -> None:
    server = MCPServerConfiguration(command="run.sh", is_builtin=True)
    assert get(McpServerService).is_local(server) is False


def test_is_local_false_without_command() -> None:
    server = MCPServerConfiguration(command="", is_builtin=False)
    assert get(McpServerService).is_local(server) is False


def test_category_label_uses_display() -> None:
    assert get(ToolService).category_label(ToolConfiguration(category="querying")) == "Querying"


def test_category_label_falls_back_to_other() -> None:
    assert get(ToolService).category_label(ToolConfiguration(category="")) == "Other"
