"""AgentConfiguration and DocGenerationLog models."""

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import generate_agt_id, generate_dgl_id
from .fields import EncryptedTextField


class AgentConfiguration(models.Model):
    """Admin-configurable AI agent settings."""

    class Meta:
        verbose_name = "agent configuration"
        verbose_name_plural = "agent configurations"
        ordering = ["-is_active", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    AGENT_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("codex", "Codex CLI"),
        ("claude_code", "Claude Code CLI"),
        ("codex_api", "Codex CLI (API key)"),
        ("claude_code_api", "Claude Code CLI (API key)"),
        ("openai_platform", "OpenAI Platform"),
        ("claude_console", "Claude Console"),
        ("openai_api", "OpenAI-compatible API (Custom)"),
        ("ollama", "Local LLM with Ollama"),
        ("openrouter", "OpenRouter (Gateway)"),
    ]

    # Integration option categories, grouped by integration *mechanism*. The CLI
    # categories wrap a CLI subprocess; "Direct API Agent" covers every type that
    # runs the in-process OpenAICompatibleAgent loop (OpenAI, Anthropic's
    # OpenAI-compatible endpoint, OpenRouter, a local Ollama, or any custom
    # OpenAI-compatible endpoint) — they differ only by base URL / headers / key.
    AGENT_TYPE_CATEGORIES: ClassVar[list[tuple[str, list[str]]]] = [
        ("CLI Tool with Auth Token", ["codex", "claude_code"]),
        ("CLI Tool with API Key", ["codex_api", "claude_code_api"]),
        (
            "Direct API Agent",
            ["openai_platform", "claude_console", "openrouter", "ollama", "openai_api"],
        ),
    ]

    # CLI agent types that authenticate with a subscription credential the admin
    # supplies once (stored encrypted in `auth_token`) rather than a per-token
    # API key. Codex stores an auth.json (device-code login); Claude Code stores
    # a long-lived OAuth token from `claude setup-token`.
    AUTH_TOKEN_AGENT_TYPES: ClassVar[set[str]] = {"codex", "claude_code"}

    # Agent types that run in-process (no Codex container) and call a provider
    # HTTP API directly. They have no AGENTS.md container to sync to.
    DIRECT_API_AGENT_TYPES: ClassVar[set[str]] = {
        "openai_platform",
        "claude_console",
        "openai_api",
        "ollama",
        "openrouter",
    }

    __prefix__: ClassVar[str] = "agt"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_agt_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(
        verbose_name="is active", default=False, help_text="Only one agent can be active at a time"
    )

    # Domain
    name = models.CharField(max_length=100, help_text="Display name for this agent configuration")
    agent_type = models.CharField(
        verbose_name="agent type", max_length=50, choices=AGENT_TYPE_CHOICES, default="codex"
    )
    system_prompt = models.TextField(
        verbose_name="system prompt",
        blank=True,
        help_text="System prompt / AGENTS.md content sent to the AI agent",
    )
    auth_token = EncryptedTextField(
        verbose_name="auth token",
        blank=True,
        default="",
        db_column="auth_token",
        help_text="Encrypted auth.json content from ChatGPT subscription sign-in (device-code login)",  # noqa: E501
    )
    api_key = EncryptedTextField(
        verbose_name="API key",
        blank=True,
        default="",
        db_column="api_key",
        help_text="Encrypted provider API key (e.g. OpenAI) for API-key CLI authentication",
    )
    service_url = models.URLField(
        verbose_name="service URL",
        blank=True,
        default="",
        help_text="Override for this agent's service URL (e.g. the Codex API gateway). "
        "Leave blank to fall back to the system-wide Codex Service URL or the "
        "CODEX_SERVICE_URL environment variable.",
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Backend-specific settings. For direct API agents: "
        "`model`, `base_url`, and optional `max_tokens`.",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.get_agent_type_display()})"


class DocGenerationLog(models.Model):
    """Audit log for AI documentation generation."""

    class Meta:
        verbose_name = "doc generation log"
        verbose_name_plural = "doc generation logs"
        ordering = ["-started_at"]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("running", "Running"),
        ("success", "Success"),
        ("partial", "Partial"),
        ("failed", "Failed"),
    ]

    __prefix__: ClassVar[str] = "dgl"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_dgl_id, editable=False)

    # Time
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(verbose_name="completed at", null=True, blank=True)

    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")

    # Domain
    destination = models.CharField(max_length=500)
    filename = models.CharField(max_length=255, blank=True)
    doc_type = models.CharField(verbose_name="doc type", max_length=50)
    is_library = models.BooleanField(
        verbose_name="is library",
        default=False,
        help_text="True when this run generated a multi-file documentation library "
        "(a folder tree) rather than a single file.",
    )
    execution_time_ms = models.IntegerField(verbose_name="execution time ms", null=True, blank=True)
    source_databases = models.JSONField(verbose_name="source databases", default=list, blank=True)
    source_docs = models.JSONField(verbose_name="source docs", default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    error_message = models.TextField(verbose_name="error message", blank=True)
    file_size = models.IntegerField(verbose_name="file size", null=True, blank=True)
    prompt_used = models.TextField(verbose_name="prompt used", blank=True)
    agent_output = models.TextField(verbose_name="agent output", blank=True)

    # Relations
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    agent = models.ForeignKey(
        "AgentConfiguration", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self) -> str:
        label = f"{self.destination}/ (library)" if self.is_library else self.filename
        return f"{label} — {self.status} ({self.started_at})"
