"""ChatSession and ChatMessage models for chat history."""

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import generate_msg_id, generate_ses_id


class ChatSession(models.Model):
    """Stores chat session history."""

    class Meta:
        verbose_name = "chat session"
        verbose_name_plural = "chat sessions"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="idx_%(class)s_user_recent"),
        ]

    __prefix__: ClassVar[str] = "ses"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_ses_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Domain
    title = models.CharField(max_length=200, blank=True)

    # Relations
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")

    def __str__(self) -> str:
        return self.title or f"Session {self.pk}"


class ChatMessage(models.Model):
    """Stores individual chat messages."""

    class Meta:
        verbose_name = "chat message"
        verbose_name_plural = "chat messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="idx_%(class)s_session_time"),
        ]

    ROLE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    __prefix__: ClassVar[str] = "msg"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_msg_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)

    # State
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    # Domain
    content = models.TextField()
    tools_used = models.JSONField(
        verbose_name="tools used",
        default=list,
        blank=True,
        help_text="List of MCP tool names used in this assistant message",
    )
    sources_used = models.JSONField(
        verbose_name="sources used",
        default=list,
        blank=True,
        help_text="List of {uri, name} dicts for MCP sources attached to this user message",
    )
    prompts_used = models.JSONField(
        verbose_name="prompts used",
        default=list,
        blank=True,
        help_text="List of {name, display_name} dicts for prompts attached to this user message",
    )

    # Relations
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}..."
