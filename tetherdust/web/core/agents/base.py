from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class BaseAgent(ABC):
    """Abstract base class for AI agent implementations.

    All agents must implement the chat method to provide streaming responses.
    Agents can support MCP (Model Context Protocol) for tool access, or use
    direct API integrations.
    """

    @abstractmethod
    def chat(
        self,
        message: str,
        user_id: int,
        session_id: str,
        allowed_tools: list[str] | None = None,
        allowed_databases: list[str] | None = None,
        allowed_doc_sources: list[str] | None = None,
        max_row_limit: int | None = None,
        timeout: float | None = None,
        custom_mcp_servers: list[dict[str, Any]] | None = None,
        history: list[dict[str, str]] | None = None,
        allowed_codebases: list[str] | None = None,
        allowed_reports: list[str] | None = None,
        allowed_dashboards: list[str] | None = None,
        allowed_tethers: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Send message and yield streaming response chunks.

        Implementations must catch transport errors internally and yield
        user-friendly error messages as final chunks rather than raising
        raw exceptions. The consumer treats any unhandled exception as a
        generic "unexpected error" — specific error context is lost.

        Args:
            message: User's input message
            user_id: ID of the user making the request (for audit logging)
            session_id: Conversation session identifier
            allowed_tools: List of MCP tool names the user can access (None = all)
            allowed_databases: List of database connection names the user can access (None = all)
            allowed_doc_sources: List of doc source names the user can access (None = all)
            allowed_codebases: List of codebase names the user can access (None = all)
            allowed_reports: List of report names the user can access (None = all)
            allowed_dashboards: List of dashboard names the user can access (None = all)
            allowed_tethers: List of tether IDs (as strings) the user can access (None = all)
            max_row_limit: Maximum rows per query for this user's role (None = no override)
            timeout: Response timeout in seconds (None = use default)
            custom_mcp_servers: Extra MCP servers the user may use. Each entry is a
                dict with keys `name`, `url`, `transport`, `auth_token`, `headers`.
                The agent backend decides how to wire these into its config.
            history: Prior conversation turns as a list of
                `{"role": "user"|"assistant", "content": str}` dicts (oldest
                first), excluding the current `message`. None = no history.
                Direct API agents send these natively; CLI agents flatten them
                into the prompt.

        Yields:
            str: Response chunks as they become available
        """
        pass

    @abstractmethod
    def supports_mcp(self) -> bool:
        """Whether this agent supports MCP tools natively.

        Returns:
            bool: True if agent can use MCP tools, False otherwise
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get human-readable name of this agent.

        Returns:
            str: Agent display name (e.g., "Codex CLI", "Claude Code")
        """
        pass

    def prepare_tool_filter(self, allowed_tools: list[str] | None) -> dict[str, bool]:
        """Convert allowed tools list to filter dictionary.

        Args:
            allowed_tools: List of tool names, or None for all tools

        Returns:
            dict: Tool name to enabled status mapping
        """
        if allowed_tools is None:
            return {}

        return {tool: True for tool in allowed_tools}

    def prepare_database_filter(self, allowed_databases: list[str] | None) -> dict[str, bool]:
        """Convert allowed databases list to filter dictionary.

        Args:
            allowed_databases: List of database names, or None for all databases

        Returns:
            dict: Database name to enabled status mapping
        """
        if allowed_databases is None:
            return {}

        return {db: True for db in allowed_databases}
