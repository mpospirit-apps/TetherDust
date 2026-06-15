"""Shared base class for the chat WebSocket consumers.

`BaseAgentConsumer` owns the pieces that both `ChatConsumer` and
`ChartEditConsumer` share:

- The cancellable agent task slot and the cancel/abort dance.
- The streaming dispatch loop that turns Codex stream chunks into
  WebSocket frames.
- The `_get_agent()` helper that reads the active `AgentConfiguration`.
- A small extension surface for subclasses (`_codex_session_id`,
  `_on_agent_cancelled`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from ..agents.stream import parse_chunk, tool_status_label

if TYPE_CHECKING:
    from ..agents.base import BaseAgent

logger = logging.getLogger(__name__)


class BaseAgentConsumer(AsyncWebsocketConsumer):
    """Common lifecycle + agent-streaming logic for chat WebSocket consumers."""

    _agent_task: asyncio.Task[None] | None = None
    _current_agent: BaseAgent | None = None

    # --- Subclass hooks -------------------------------------------------

    def _codex_session_id(self) -> str:
        """Return the session id used to address the Codex subprocess."""
        raise NotImplementedError

    async def _on_agent_cancelled(self) -> None:
        """Hook called when the agent stream is cancelled mid-flight."""
        return

    # --- Agent lookup ---------------------------------------------------

    @database_sync_to_async
    def _get_agent(self) -> BaseAgent:
        from ..agents import get_agent

        return get_agent()

    # --- Cancellation ---------------------------------------------------

    async def _cancel_agent(self) -> None:
        """Cancel the running agent task and close any open HTTP stream."""
        # Capture the agent before awaiting the task: when the turn runs as a
        # background task, its `finally` clears `_current_agent`, so reading it
        # after the await below would miss the stream we need to close.
        agent = self._current_agent

        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            try:
                await self._agent_task
            except asyncio.CancelledError:
                pass
        self._agent_task = None

        if agent and hasattr(agent, "cancel"):
            await agent.cancel()
        self._current_agent = None

        await self._abort_codex_session()

    async def _abort_codex_session(self) -> None:
        """Tell the active CLI gateway to abort the subprocess for this session.

        Closing the HTTP stream (via ``agent.cancel()``) already prompts the
        gateway to kill its subprocess; this out-of-band ``/abort`` is the
        reliable backstop when the gateway is blocked reading subprocess output.
        The target URL is resolved per the active agent type so a Claude Code
        request is aborted on the Claude gateway, not the Codex one. Direct-API
        agents have no gateway and are skipped.
        """
        try:
            session_id = self._codex_session_id()
        except NotImplementedError:
            return
        if not session_id:
            return

        from ..models import AgentConfiguration, SystemConfiguration

        config = await database_sync_to_async(AgentConfiguration.get_active)()
        agent_type = config.agent_type if config else "codex"
        if config and agent_type in AgentConfiguration.DIRECT_API_AGENT_TYPES:
            return  # no subprocess gateway to abort

        if agent_type == "claude_code":
            config_key, env_key = "claude_service_url", "CLAUDE_SERVICE_URL"
        elif agent_type == "claude_code_api":
            config_key, env_key = "claude_api_service_url", "CLAUDE_API_SERVICE_URL"
        elif agent_type == "codex_api":
            config_key, env_key = "codex_api_service_url", "CODEX_API_SERVICE_URL"
        else:
            config_key, env_key = "codex_service_url", "CODEX_SERVICE_URL"
        service_url = (
            (config.service_url if config else "")
            or await database_sync_to_async(SystemConfiguration.get_value)(config_key, "")
            or os.environ.get(env_key, "")
        ).rstrip("/")
        if not service_url:
            return

        from ..agents.gateway import gateway_auth_headers

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{service_url}/abort/{session_id}", headers=gateway_auth_headers()
                )
                data = resp.json()
                if data.get("status") == "aborted":
                    logger.info("Agent subprocess aborted for session %s", session_id)
        except Exception:
            logger.debug("Failed to abort agent session %s (may already be done)", session_id)

    # --- Streaming ------------------------------------------------------

    async def _stream_agent_response(
        self, agent: BaseAgent, **chat_kwargs: Any
    ) -> tuple[list[str], str | None]:
        """Run `agent.chat`, dispatching events to the websocket.

        Partial state is written to ``self._stream_deltas`` and
        ``self._stream_completed`` as it arrives, so a `CancelledError`
        propagating out of this coroutine still leaves the consumer with
        the buffer accumulated up to the cancel point. Returns the same
        `(deltas, completed)` tuple on normal completion.
        """
        self._stream_deltas: list[str] = []
        self._stream_completed: str | None = None
        self._stream_error: str | None = None

        async for chunk in agent.chat(**chat_kwargs):
            event = parse_chunk(chunk)
            if event.kind == "error":
                # Real failure cause — captured for session-log persistence by
                # the consumer; the user still sees the friendly text chunk.
                self._stream_error = event.text
            elif event.kind == "tool":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "stream_status",
                            "content": tool_status_label(event.text),
                        }
                    )
                )
            elif event.kind == "response":
                self._stream_completed = event.text
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "stream_chunk",
                            "content": event.text,
                        }
                    )
                )
            elif event.kind == "thinking":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "stream_status",
                            "content": event.text,
                        }
                    )
                )
            else:
                self._stream_deltas.append(event.text)
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "stream_chunk",
                            "content": event.text,
                        }
                    )
                )

        return self._stream_deltas, self._stream_completed
