"""MCP server and tool services."""

from __future__ import annotations

from ..models.connections import MCPServerConfiguration, ToolConfiguration


class McpServerService:
    """Operations on :class:`MCPServerConfiguration`."""

    def is_local(self, server: MCPServerConfiguration) -> bool:
        """True for local subprocess servers (have a command, not built-in)."""
        return bool(server.command) and not server.is_builtin


class ToolService:
    """Operations on :class:`ToolConfiguration`."""

    def category_label(self, tool: ToolConfiguration) -> str:
        """Human-readable category, falling back to 'Other' when uncategorized."""
        return tool.get_category_display() or "Other"
