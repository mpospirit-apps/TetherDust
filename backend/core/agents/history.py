"""Conversation history helpers shared across agent backends.

History reaches an agent as a structured list of turns::

    [{"role": "user" | "assistant", "content": "..."}, ...]

Direct API agents send these turns natively to the provider. CLI-wrapping
agents (Codex) take a single prompt string, so `messages_to_prompt` flattens
the turns into the same `[Conversation history]` block the chat consumer used
to build inline — preserving today's Codex behavior exactly.
"""

from __future__ import annotations

HistoryMessages = list[dict[str, str]]


def messages_to_prompt(history: HistoryMessages | None) -> str:
    """Flatten structured history turns into a prompt string.

    Returns an empty string when there is no history.
    """
    if not history:
        return ""
    lines = []
    for turn in history:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "[Conversation history]\n" + "\n\n".join(lines) + "\n[End of history]"
