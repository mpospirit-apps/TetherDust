"""WebSocket consumer for the main chat UI."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from engine.consumers.audit import log_queries_from_response
from engine.consumers.base import BaseAgentConsumer
from engine.consumers.mcp_client import fetch_tools_called, read_mcp_resources
from engine.consumers.permissions import PermissionsMixin
from engine.consumers.session import SessionMixin

logger = logging.getLogger(__name__)


# Tools that are only callable via the chart edit panel and must never
# be exposed via the general chat, regardless of role configuration.
_CHART_EDIT_ONLY_TOOLS = frozenset({"update_chart"})


class ChatConsumer(SessionMixin, PermissionsMixin, BaseAgentConsumer):
    """WebSocket consumer for streaming AI agent responses."""

    def _codex_session_id(self) -> str:
        if not getattr(self, "chat_session", None):
            return ""
        return str(self.chat_session.id)

    def _partial_text(self) -> str:
        """Best-effort assistant text accumulated so far this turn."""
        completed = getattr(self, "_stream_completed", None)
        deltas = getattr(self, "_stream_deltas", [])
        return completed or ("".join(deltas) if deltas else "")

    async def _on_agent_cancelled(self) -> None:
        """Persist any partial assistant output before bowing out."""
        partial = self._partial_text()
        if partial:
            await self._save_message("assistant", partial + "\n\n*(interrupted)*")

    async def connect(self) -> None:
        self.user = self.scope["user"]

        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.session_id = self.scope["url_route"]["kwargs"].get("session_id")
        self.chat_session = await self._get_or_create_session()

        self.profile = await self._get_user_profile()
        profile_id = self.profile.id if self.profile else None
        role_name = self.profile.role.name if self.profile and self.profile.role else None
        logger.debug("user=%s, profile_id=%s, role=%s", self.user.username, profile_id, role_name)
        if not self.profile:
            logger.debug("NO PROFILE — user will have no permissions")

        if not await self._user_can_chat():
            logger.info("Chat access denied for user=%s (role=%s)", self.user.username, role_name)
            await self.close(code=4003)
            return

        self.allowed_tools = await self._get_allowed_tools()
        logger.debug(
            "allowed_tools=%s (type=%s, len=%s)",
            self.allowed_tools,
            type(self.allowed_tools).__name__,
            len(self.allowed_tools) if self.allowed_tools else 0,
        )

        self.allowed_databases = await self._get_allowed_databases()
        logger.debug("allowed_databases=%s", self.allowed_databases)

        self.allowed_doc_sources = await self._get_allowed_doc_sources()
        logger.debug("allowed_doc_sources=%s", self.allowed_doc_sources)

        self.allowed_codebases = await self._get_allowed_codebases()
        logger.debug("allowed_codebases=%s", self.allowed_codebases)

        self.allowed_reports = await self._get_allowed_reports()
        logger.debug("allowed_reports=%s", self.allowed_reports)

        self.allowed_dashboards = await self._get_allowed_dashboards()
        logger.debug("allowed_dashboards=%s", self.allowed_dashboards)

        self.allowed_tethers = await self._get_allowed_tethers()
        logger.debug("allowed_tethers=%s", self.allowed_tethers)

        self.max_row_limit = await self._get_max_row_limit()
        logger.debug("max_row_limit=%s", self.max_row_limit)

        self.allowed_mcp_servers = await self._get_allowed_mcp_servers()
        logger.debug(
            "allowed_mcp_servers=%s",
            [s["name"] for s in self.allowed_mcp_servers],
        )

        await self.accept()

        await self.send(
            text_data=json.dumps(
                {
                    "type": "session_info",
                    "session_id": self.chat_session.id,
                    "title": self.chat_session.title,
                }
            )
        )

        messages = await self._get_session_messages()
        if messages:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "history",
                        "messages": messages,
                    }
                )
            )

    async def disconnect(self, code: int) -> None:
        try:
            await asyncio.wait_for(self._cancel_agent(), timeout=10)
        except TimeoutError:
            logger.warning("Agent cancellation timed out during disconnect")

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid message format",
                    }
                )
            )
            return

        # Control frame: stop the in-flight generation.
        if data.get("type") == "cancel":
            await self._cancel_agent()
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "stream_cancelled",
                        "content": self._partial_text(),
                    }
                )
            )
            return

        message = data.get("message", "").strip()
        if not message:
            return

        # One turn at a time. The UI disables input while streaming, but guard
        # against a race where a second message arrives before the first ends.
        if self._agent_task and not self._agent_task.done():
            return

        # Run the turn in a background task so the receive loop stays free to
        # process a `cancel` frame mid-stream. Channels dispatches frames
        # serially per consumer, so awaiting the stream inline here would block
        # cancellation until the response finished.
        self._agent_task = asyncio.create_task(self._run_turn(data, message))

    async def _run_turn(self, data: dict[str, Any], message: str) -> None:
        resource_uris = data.get("resource_uris")
        prompt_context = data.get("prompt_context")
        sources_info = data.get("sources_info") or []
        prompts_info = data.get("prompts_info") or []

        effective_tools = self.allowed_tools

        # Load conversation history BEFORE saving the new message (so it
        # contains only prior turns, not the current one). Passed to the agent
        # as structured turns; multi-turn agents send them natively, CLI agents
        # flatten them into the prompt.
        history_messages = await self._get_conversation_messages()

        await self._save_message(
            "user",
            message,
            sources_used=sources_info,
            prompts_used=prompts_info,
        )

        # Derive the session title from the first user message up front, so it
        # is set even if the turn is cancelled before the response completes.
        await self._maybe_set_title(message)

        agent_message = message
        if resource_uris and isinstance(resource_uris, list):
            resource_context = await read_mcp_resources(
                self.allowed_doc_sources,
                resource_uris,
            )
            if resource_context:
                agent_message = resource_context + "\n\n" + agent_message

        if prompt_context and isinstance(prompt_context, list):
            context_parts = [p for p in prompt_context if isinstance(p, str) and p.strip()]
            if context_parts:
                prompt_text = "\n\n".join(
                    f"[Prompt Instructions]\n{part}" for part in context_parts
                )
                agent_message = prompt_text + "\n\n" + agent_message

        try:
            agent = await self._get_agent()
        except (RuntimeError, ValueError) as e:
            error_msg = f"Agent unavailable: {e}"
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": error_msg,
                    }
                )
            )
            await self._safe_save_message("system", error_msg)
            return
        except Exception:
            logger.exception("Unexpected error initializing agent")
            error_msg = (
                "An unexpected error occurred while initializing the AI agent. Please try again."
            )
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": error_msg,
                    }
                )
            )
            await self._safe_save_message("system", error_msg)
            return

        self._current_agent = agent

        await self.send(text_data=json.dumps({"type": "stream_start"}))

        # Build the permission args sent to the agent. Scope-restricted
        # tools (like update_chart) are stripped here so regular chat can
        # never invoke them even if a role has them enabled — they are
        # only reachable via the chart edit panel.
        if effective_tools is not None:
            tools_arg = [t for t in effective_tools if t not in _CHART_EDIT_ONLY_TOOLS]
        else:
            all_enabled = await self._get_all_enabled_tools()
            tools_arg = [t for t in all_enabled if t not in _CHART_EDIT_ONLY_TOOLS]
        dbs_arg = list(self.allowed_databases) if self.allowed_databases is not None else None
        docs_arg = list(self.allowed_doc_sources) if self.allowed_doc_sources is not None else None
        codebases_arg = list(self.allowed_codebases) if self.allowed_codebases is not None else None
        reports_arg = list(self.allowed_reports) if self.allowed_reports is not None else None
        dashboards_arg = (
            list(self.allowed_dashboards) if self.allowed_dashboards is not None else None
        )
        tethers_arg = list(self.allowed_tethers) if self.allowed_tethers is not None else None

        logger.debug(
            "Sending to agent: allowed_tools=%s, allowed_databases=%s, "
            "allowed_doc_sources=%s, max_row_limit=%s",
            tools_arg,
            dbs_arg,
            docs_arg,
            self.max_row_limit,
        )

        full_response: list[str] = []
        completed_response: str | None = None
        try:
            full_response, completed_response = await self._stream_agent_response(
                agent,
                message=agent_message,
                user_id=self.user.id,
                session_id=str(self.chat_session.id),
                allowed_tools=tools_arg,
                allowed_databases=dbs_arg,
                allowed_doc_sources=docs_arg,
                allowed_codebases=codebases_arg,
                allowed_reports=reports_arg,
                allowed_dashboards=dashboards_arg,
                allowed_tethers=tethers_arg,
                max_row_limit=self.max_row_limit,
                custom_mcp_servers=self.allowed_mcp_servers,
                history=history_messages,
            )
        except asyncio.CancelledError:
            logger.info("Agent task cancelled (stop or disconnect)")
            await self._on_agent_cancelled()
            return
        except Exception:
            logger.exception("Agent error during chat")
            error_msg = "An unexpected error occurred. Please try again."
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": error_msg,
                    }
                )
            )
            await self._safe_save_message("system", error_msg)
            return
        finally:
            self._agent_task = None
            self._current_agent = None

        complete_response = completed_response or ("".join(full_response) if full_response else "")

        # Persist the real agent failure cause (e.g. an unsupported-model or
        # auth error from Codex) to the session log so admins can see it in
        # control panel → Sessions. The user only saw the friendly message.
        stream_error = getattr(self, "_stream_error", None)
        if stream_error:
            logger.warning("Agent error (session=%s): %s", self.chat_session.id, stream_error)
            await self._safe_save_message("system", f"Agent error: {stream_error}")

        used_tools: list[str] = []
        try:
            # Scope the tool-call fetch to this turn's filter token so concurrent
            # chats never see each other's tool calls.
            used_tools = await fetch_tools_called(getattr(agent, "_last_filter_token", None))
            logger.debug("used_tools from MCP = %s", used_tools)

            if complete_response:
                await self._save_message(
                    "assistant",
                    complete_response,
                    tools_used=used_tools,
                )
                await log_queries_from_response(self.user, complete_response)
        except Exception:
            logger.exception("Error in post-streaming processing")

        await self.send(
            text_data=json.dumps(
                {
                    "type": "stream_end",
                    "tools": used_tools,
                    "content": complete_response,
                }
            )
        )
