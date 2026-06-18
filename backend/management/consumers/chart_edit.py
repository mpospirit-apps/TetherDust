"""WebSocket consumer for the AI-assisted chart editor.

Differences vs ChatConsumer:
- Scoped to a single Chart (chart_id in URL).
- No persistent ChatSession/ChatMessage history (ephemeral transcript).
- Injects current chart state into every prompt so the agent always sees
  fresh field values, even if the user just edited them manually or a
  prior AI turn changed them.
- Tool filter locked to: update_chart + read-only schema tools.
- Database filter locked to the chart's own database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import cast

from channels.db import database_sync_to_async
from django.contrib.auth.models import AbstractUser
from engine.consumers.base import BaseAgentConsumer
from engine.prompts import build_chart_edit_prompt

logger = logging.getLogger(__name__)


class ChartEditConsumer(BaseAgentConsumer):
    user: AbstractUser

    # Tools the agent is allowed to call from the chart edit panel.
    _CHART_EDIT_TOOLS = [
        "update_chart",
        "query_database",
        "list_tables",
        "get_table_schema",
        "get_query_examples",
        "list_databases",
        "search_docs",
    ]

    def _codex_session_id(self) -> str:
        return f"chart-edit-{self.chart_id}-{self.user.pk}"

    async def connect(self) -> None:
        self.user = cast(AbstractUser, self.scope["user"])

        if not self.user or self.user.is_anonymous or not self.user.is_staff:
            await self.close(code=4001)
            return

        chart_id_raw = self.scope["url_route"]["kwargs"].get("chart_id")
        if chart_id_raw is None:
            await self.close(code=4002)
            return
        try:
            self.chart_id = int(chart_id_raw)
        except (TypeError, ValueError):
            await self.close(code=4002)
            return

        chart_info = await self._get_chart_info(self.chart_id)
        if not chart_info:
            await self.close(code=4004)
            return
        self._chart_database_name = chart_info["database_name"]

        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "ready",
                    "chart_id": self.chart_id,
                }
            )
        )

    async def disconnect(self, code: int) -> None:
        try:
            await asyncio.wait_for(self._cancel_agent(), timeout=10)
        except TimeoutError:
            logger.warning("ChartEdit agent cancellation timed out")

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

        user_message = (data.get("message") or "").strip()
        if not user_message:
            return

        # Always re-read the chart state so the agent sees fresh values.
        chart_info = await self._get_chart_info(self.chart_id)
        if not chart_info:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Chart no longer exists.",
                    }
                )
            )
            return

        agent_message = build_chart_edit_prompt(chart_info, user_message)

        try:
            agent = await self._get_agent()
        except Exception as e:
            logger.exception("Failed to initialize agent for chart edit")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": f"Agent unavailable: {e}",
                    }
                )
            )
            return

        self._current_agent = agent
        await self.send(text_data=json.dumps({"type": "stream_start"}))

        self._agent_task = asyncio.current_task()
        full_response: list[str] = []
        completed_response: str | None = None
        try:
            full_response, completed_response = await self._stream_agent_response(
                agent,
                message=agent_message,
                user_id=self.user.pk,
                session_id=self._codex_session_id(),
                allowed_tools=list(self._CHART_EDIT_TOOLS),
                allowed_databases=[self._chart_database_name],
                allowed_doc_sources=[],
                allowed_codebases=[],
                max_row_limit=1000,
            )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Agent error during chart edit")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "The AI editor hit an unexpected error. Please try again.",
                    }
                )
            )
            return
        finally:
            self._agent_task = None
            self._current_agent = None

        complete_response = completed_response or ("".join(full_response) if full_response else "")
        await self.send(
            text_data=json.dumps(
                {
                    "type": "stream_end",
                    "content": complete_response,
                }
            )
        )

    @database_sync_to_async
    def _get_chart_info(self, chart_id: int) -> dict[str, object] | None:
        from engine.models import Chart

        try:
            chart = Chart.objects.select_related("database").get(pk=chart_id)
        except Chart.DoesNotExist:
            return None
        return {
            "chart_id": chart.pk,
            "title": chart.title,
            "description": chart.description or "",
            "database_name": chart.database.name,
            "sql_query": chart.sql_query,
            "custom_d3_code": chart.custom_d3_code or "",
        }
