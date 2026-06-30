"""In-process MCP client helpers for Direct API agents.

The MCP server only speaks the MCP protocol over streamable-HTTP — there is no
plain `GET /tools` / `POST /call_tool` REST surface. A Direct API agent therefore
drives a real `ClientSession` (the same SDK `containers/local_mcp/local_mcp_api.py`
uses over stdio, here over HTTP) to discover and invoke tools.

`open_mcp_session` yields an initialized session; `mcp_tools_to_openai` converts
the MCP tool catalog into the OpenAI function-calling schema; `call_tool_text`
flattens a tool result into a string for the message history.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, ListToolsResult


@asynccontextmanager
async def open_mcp_session(
    url: str, headers: dict[str, str] | None = None
) -> AsyncGenerator[ClientSession, None]:
    """Open and initialize an MCP `ClientSession` against a streamable-HTTP URL.

    `url` is the tokenized (`.../mcp/<token>`) or unrestricted (`.../mcp`) MCP
    endpoint. The session and its transport are torn down on exit — including
    when the surrounding task is cancelled.
    """
    if headers:
        async with httpx.AsyncClient(headers=headers) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
    else:
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


def mcp_tools_to_openai(tools_result: ListToolsResult) -> list[dict[str, Any]]:
    """Convert an MCP tool catalog into OpenAI `tools` (function) definitions."""
    tools: list[dict[str, Any]] = []
    for tool in tools_result.tools:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    return tools


def call_tool_text(result: CallToolResult) -> str:
    """Flatten an MCP tool result into a string for the LLM message history."""
    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            # Non-text content (image/resource/etc.) — serialize a compact repr.
            dump = getattr(block, "model_dump", None)
            parts.append(json.dumps(dump()) if callable(dump) else str(block))
    if not parts and getattr(result, "structuredContent", None) is not None:
        return json.dumps(result.structuredContent)
    return "\n".join(parts)
