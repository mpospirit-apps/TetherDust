"""ChatSession and ChatMessage models for chat history."""

from django.contrib.auth.models import User
from django.db import models


class ChatSession(models.Model):
    """Stores chat session history."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Session {self.pk}"


class ChatMessage(models.Model):
    """Stores individual chat messages."""

    ROLE_CHOICES: list[tuple[str, str]] = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tools_used = models.JSONField(
        default=list,
        blank=True,
        help_text="List of MCP tool names used in this assistant message",
    )
    sources_used = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {uri, name} dicts for MCP sources attached to this user message",
    )
    prompts_used = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {name, display_name} dicts for prompts attached to this user message",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}..."
