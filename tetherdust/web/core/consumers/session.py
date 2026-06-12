"""Session and message persistence helpers for `ChatConsumer`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from channels.db import database_sync_to_async

if TYPE_CHECKING:

    class _Base:
        user: Any
        session_id: Any
        chat_session: Any
else:
    _Base = object

logger = logging.getLogger(__name__)


class SessionMixin(_Base):
    """Async helpers for ChatSession / ChatMessage persistence.

    Expects the consumer to expose ``self.user`` and ``self.session_id``
    on connect, and ``self.chat_session`` once `_get_or_create_session`
    has run.
    """

    @database_sync_to_async
    def _get_or_create_session(self) -> object:
        from ..models import ChatSession

        if self.session_id:
            try:
                return ChatSession.objects.get(id=self.session_id, user=self.user)
            except (ChatSession.DoesNotExist, ValueError):
                pass

        return ChatSession.objects.create(user=self.user)

    @database_sync_to_async
    def _get_session_messages(self) -> list[dict[str, object]]:
        # `system` messages carry the real agent failure cause (e.g. an
        # invalid-model or auth error). They are never shown inline in the chat
        # transcript — admins review them in control panel → Sessions.
        messages = self.chat_session.messages.exclude(role="system").values(
            "role",
            "content",
            "tools_used",
            "sources_used",
            "prompts_used",
            "created_at",
        )
        result = []
        for msg in messages:
            entry: dict = {
                "role": msg["role"],
                "content": msg["content"],
                "created_at": msg["created_at"].isoformat(),
            }
            if msg["role"] == "assistant" and msg["tools_used"]:
                entry["tools"] = msg["tools_used"]
            if msg["role"] == "user":
                if msg["sources_used"]:
                    entry["sources"] = msg["sources_used"]
                if msg["prompts_used"]:
                    entry["prompts"] = msg["prompts_used"]
            result.append(entry)
        return result

    @database_sync_to_async
    def _save_message(
        self,
        role: str,
        content: str,
        tools_used: list[str] | None = None,
        sources_used: list[str] | None = None,
        prompts_used: list[str] | None = None,
    ) -> object:
        from ..models import ChatMessage

        return ChatMessage.objects.create(
            session=self.chat_session,
            role=role,
            content=content,
            tools_used=tools_used or [],
            sources_used=sources_used or [],
            prompts_used=prompts_used or [],
        )

    async def _safe_save_message(self, role: str, content: str) -> None:
        """Save a message, logging any DB error instead of raising."""
        try:
            await self._save_message(role, content)
        except Exception:
            logger.exception("Failed to save %s message to DB", role)

    @database_sync_to_async
    def _maybe_set_title(self, first_message: str) -> None:
        if not self.chat_session.title:
            title = first_message[:100] + ("..." if len(first_message) > 100 else "")
            self.chat_session.title = title
            self.chat_session.save(update_fields=["title"])

    @database_sync_to_async
    def _get_conversation_messages(
        self, max_messages: int = 20, max_chars: int = 8000
    ) -> list[dict[str, str]]:
        """Return recent history as structured turns for multi-turn agents.

        Each entry is `{"role": "user"|"assistant", "content": str}`, oldest
        first, excluding the current (not-yet-saved) turn. Recent messages are
        kept up to `max_messages` turns / `max_chars` total characters.
        """
        messages = list(
            self.chat_session.messages.exclude(role="system")
            .order_by("created_at")
            .values_list("role", "content")
        )
        if not messages:
            return []

        turns: list[dict] = []
        total = 0
        for role, content in reversed(messages):
            normalized = "user" if role == "user" else "assistant"
            if total + len(content) > max_chars:
                break
            turns.append({"role": normalized, "content": content})
            total += len(content)
            if len(turns) >= max_messages:
                break
        turns.reverse()
        return turns
