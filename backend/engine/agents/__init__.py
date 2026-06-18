from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .base import BaseAgent

if TYPE_CHECKING:
    from ..models import AgentConfiguration


def build_agent(config: AgentConfiguration) -> BaseAgent:
    """Instantiate the agent class for a given AgentConfiguration.

    Shared by `get_agent()` (active config) and callers that build a derived
    config (e.g. tether generation clones the active config with a custom
    system prompt). Selecting the class by `agent_type` keeps credential
    handling correct for every agent type.

    Raises:
        ValueError: If the config's agent type is unknown
    """
    # Import the backends lazily so a bare `import engine.agents` stays light:
    # their httpx / gateway / MCP dependency chains load only when an agent is
    # actually built. (No cycles exist — none of them import this package.)
    from .claude import ClaudeCodeAgent, ClaudeCodeApiAgent
    from .codex import CodexAgent, CodexApiAgent
    from .direct_api import (
        ClaudeConsoleAgent,
        OllamaAgent,
        OpenAICompatibleAgent,
        OpenAIPlatformAgent,
        OpenRouterAgent,
    )

    agents: dict[str, Callable[..., BaseAgent]] = {
        "codex": CodexAgent,
        "claude_code": ClaudeCodeAgent,
        "claude_code_api": ClaudeCodeApiAgent,
        "codex_api": CodexApiAgent,
        "openai_platform": OpenAIPlatformAgent,
        "claude_console": ClaudeConsoleAgent,
        "openai_api": OpenAICompatibleAgent,
        "ollama": OllamaAgent,
        "openrouter": OpenRouterAgent,
        # Future agent implementations:
        # "gemini": GeminiAgent,
    }

    agent_type = config.agent_type
    if agent_type not in agents:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(agents.keys())}")

    return agents[agent_type](config=config)


def get_agent() -> BaseAgent:
    """Factory function to get configured agent from database.

    Reads the active AgentConfiguration and returns the corresponding
    agent instance. Falls back to CodexAgent with no config if none exists.

    Returns:
        BaseAgent: Configured agent instance

    Raises:
        ValueError: If configured agent type is unknown
    """
    from engine.services import AgentService, get

    config = get(AgentService).get_active()
    if not config:
        from .codex import CodexAgent

        return CodexAgent()

    return build_agent(config)


def get_available_agents() -> dict[str, str]:
    """Get dictionary of available agent IDs and display names.

    Returns:
        dict: Mapping of agent ID to display name
    """
    return {
        "codex": "Codex CLI (ChatGPT Plus/Pro)",
        "claude_code": "Claude Code CLI (Pro/Max)",
        "codex_api": "Codex CLI (API key)",
        "claude_code_api": "Claude Code CLI (API key)",
        "openai_platform": "OpenAI Platform",
        "claude_console": "Claude Console",
        "openai_api": "OpenAI-compatible API (Custom)",
        "ollama": "Local LLM with Ollama",
        "openrouter": "OpenRouter (Gateway)",
        # Future agents:
        # "gemini": "Google Gemini API",
    }


__all__ = ["BaseAgent", "build_agent", "get_agent", "get_available_agents"]
