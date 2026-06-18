"""Agent stream chunk protocol.

Agents emit a flat string stream where structured events are framed by
NUL-prefixed markers:

    \x00TOOL:<name>       agent is invoking an MCP tool
    \x00RESPONSE:<text>   canonical completed response payload
    \x00THINKING:<text>   model thinking trace (status only, not part of answer)
    \x00ERROR:<text>      real failure cause (logged to the session, not shown)
    <plain text>          partial response token

The producer is `agents/codex.py`; consumers should use `parse_chunk` rather
than re-implementing the prefix split at every call site.
"""

from dataclasses import dataclass
from typing import Literal

TOOL_PREFIX = "\x00TOOL:"
RESPONSE_PREFIX = "\x00RESPONSE:"
THINKING_PREFIX = "\x00THINKING:"
ERROR_PREFIX = "\x00ERROR:"

EventKind = Literal["tool", "response", "thinking", "error", "text"]


@dataclass(frozen=True)
class AgentEvent:
    kind: EventKind
    text: str


def parse_chunk(chunk: str) -> AgentEvent:
    if chunk.startswith(TOOL_PREFIX):
        return AgentEvent("tool", chunk[len(TOOL_PREFIX) :])
    if chunk.startswith(RESPONSE_PREFIX):
        return AgentEvent("response", chunk[len(RESPONSE_PREFIX) :])
    if chunk.startswith(THINKING_PREFIX):
        return AgentEvent("thinking", chunk[len(THINKING_PREFIX) :])
    if chunk.startswith(ERROR_PREFIX):
        return AgentEvent("error", chunk[len(ERROR_PREFIX) :])
    return AgentEvent("text", chunk)


def tool_status_label(tool_name: str) -> str:
    """`list_tables` -> `Calling List Tables…`."""
    return f"Calling {tool_name.replace('_', ' ').title()}…"


def scrub_markers(text: str) -> str:
    """Replace markers with human-readable tags for log excerpts and strip NULs."""
    if not text:
        return ""
    return (
        text.replace(THINKING_PREFIX, "[think] ")
        .replace(RESPONSE_PREFIX, "[reply] ")
        .replace(TOOL_PREFIX, "[tool] ")
        .replace(ERROR_PREFIX, "[error] ")
        .replace("\x00", " ")
    )
