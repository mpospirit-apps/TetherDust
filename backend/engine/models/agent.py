"""AgentConfiguration and DocGenerationLog models."""

import base64
import datetime
import json
import os
from typing import Any

from django.contrib.auth.models import User
from django.db import models

from ._encryption import decrypt_value, encrypt_value
from .connections import SystemConfiguration


def _decode_jwt_claims(token: str | None) -> dict[str, object] | None:
    """Best-effort decode of a JWT payload without signature verification.

    Used only to surface identity/expiry claims for display; we never trust
    these for access decisions. Returns None on any unexpected shape.
    """
    if not token or token.count(".") != 2:
        return None
    payload_seg = token.split(".")[1]
    payload_seg += "=" * (-len(payload_seg) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload_seg))
    except Exception:
        return None
    return claims if isinstance(claims, dict) else None


class AgentConfiguration(models.Model):
    """Admin-configurable AI agent settings."""

    AGENT_TYPE_CHOICES = [
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
    AGENT_TYPE_CATEGORIES = [
        ("CLI Tool with Auth Token", ["codex", "claude_code"]),
        ("CLI Tool with API Key", ["codex_api", "claude_code_api"]),
        (
            "Direct API Agent",
            ["openai_platform", "claude_console", "openrouter", "ollama", "openai_api"],
        ),
    ]

    # CLI agent types that authenticate with a subscription credential the admin
    # supplies once (stored encrypted in `_auth_token`) rather than a per-token
    # API key. Codex stores an auth.json (device-code login); Claude Code stores
    # a long-lived OAuth token from `claude setup-token`.
    AUTH_TOKEN_AGENT_TYPES = {"codex", "claude_code"}

    # Agent types that run in-process (no Codex container) and call a provider
    # HTTP API directly. They have no AGENTS.md container to sync to.
    DIRECT_API_AGENT_TYPES = {
        "openai_platform",
        "claude_console",
        "openai_api",
        "ollama",
        "openrouter",
    }

    name = models.CharField(
        max_length=100, unique=True, help_text="Display name for this agent configuration"
    )
    agent_type = models.CharField(max_length=50, choices=AGENT_TYPE_CHOICES, default="codex")
    is_active = models.BooleanField(
        default=False, help_text="Only one agent can be active at a time"
    )
    system_prompt = models.TextField(
        blank=True, help_text="System prompt / AGENTS.md content sent to the AI agent"
    )
    _auth_token = models.TextField(
        blank=True,
        default="",
        db_column="auth_token",
        help_text="Encrypted auth.json content from ChatGPT subscription sign-in (device-code login)",  # noqa: E501
    )
    _api_key = models.TextField(
        blank=True,
        default="",
        db_column="api_key",
        help_text="Encrypted provider API key (e.g. OpenAI) for API-key CLI authentication",
    )
    service_url = models.URLField(
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        verbose_name = "Agent Configuration"
        verbose_name_plural = "Agent Configurations"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_agent_type_display()})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.is_active:
            # Deactivate all other agents when this one becomes active
            AgentConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)
        self._sync_agents_md()

    def _sync_agents_md(self) -> None:
        """Push the system prompt to this agent's container AGENTS.md file."""
        if not self.system_prompt:
            return
        # Direct API agents run in-process; there is no container to receive
        # AGENTS.md. The system prompt is sent inline per request instead.
        if self.agent_type in self.DIRECT_API_AGENT_TYPES:
            return
        import logging

        import httpx

        logger = logging.getLogger(__name__)
        # Prefer this agent's own service_url so a non-default container (e.g. the
        # profiled codex-api service) receives its prompt; fall back to the
        # system-wide URL / env var for this agent type when left blank. The
        # fallback must be type-aware so a blank-URL Claude agent never pushes its
        # prompt to the Codex container (and vice versa).
        if self.agent_type == "claude_code":
            config_key, env_key = "claude_service_url", "CLAUDE_SERVICE_URL"
        elif self.agent_type == "claude_code_api":
            config_key, env_key = "claude_api_service_url", "CLAUDE_API_SERVICE_URL"
        elif self.agent_type == "codex_api":
            config_key, env_key = "codex_api_service_url", "CODEX_API_SERVICE_URL"
        else:
            config_key, env_key = "codex_service_url", "CODEX_SERVICE_URL"
        service_url = (
            self.service_url
            or SystemConfiguration.get_value(config_key, "")
            or os.environ.get(env_key, "")
        ).rstrip("/")
        if not service_url:
            return
        from engine.agents.gateway import gateway_auth_headers

        try:
            with httpx.Client(timeout=5) as client:
                client.post(
                    f"{service_url}/update-agents-md",
                    json={"content": self.system_prompt},
                    headers=gateway_auth_headers(),
                ).raise_for_status()
            logger.info("Synced system prompt to %s service", self.agent_type)
        except Exception:
            logger.warning(
                "Failed to sync system prompt to %s service", self.agent_type, exc_info=True
            )

    def get_auth_token(self) -> str:
        """Return the decrypted auth token (auth.json content)."""
        return decrypt_value(self._auth_token)

    def set_auth_token(self, value: str) -> None:
        """Encrypt and store the auth token."""
        self._auth_token = encrypt_value(value) if value else ""

    def get_auth_info(self) -> dict[str, object] | None:
        """Decode the stored ChatGPT credential for display.

        Returns a dict with any of `email`, `plan`, `expires_at` (a timezone-aware
        datetime) that could be parsed from the encrypted `auth.json`, or None
        when no credential is stored / it can't be decoded. Identity claims come
        from the id_token; expiry from the short-lived access_token. These are
        for display only and are never used for access decisions.
        """
        raw = self.get_auth_token()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(tokens, dict):
            return None

        info: dict[str, object] = {}
        id_claims = _decode_jwt_claims(tokens.get("id_token"))
        if id_claims:
            email = id_claims.get("email")
            if email:
                info["email"] = email
            auth_claims = id_claims.get("https://api.openai.com/auth")
            if isinstance(auth_claims, dict):
                plan = auth_claims.get("chatgpt_plan_type")
                if plan:
                    info["plan"] = plan

        access_claims = _decode_jwt_claims(tokens.get("access_token"))
        exp = access_claims.get("exp") if access_claims else None
        if isinstance(exp, (int, float)):
            info["expires_at"] = datetime.datetime.fromtimestamp(exp, tz=datetime.UTC)

        return info or None

    def get_api_key(self) -> str:
        """Return the decrypted provider API key."""
        return decrypt_value(self._api_key)

    def set_api_key(self, value: str) -> None:
        """Encrypt and store the provider API key."""
        self._api_key = encrypt_value(value) if value else ""

    @classmethod
    def get_active(cls) -> "AgentConfiguration | None":
        """Return the currently active agent configuration, or None."""
        return cls.objects.filter(is_active=True).first()


class DocGenerationLog(models.Model):
    """Audit log for AI documentation generation."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("success", "Success"),
        ("partial", "Partial"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    agent = models.ForeignKey(
        "AgentConfiguration", on_delete=models.SET_NULL, null=True, blank=True
    )
    destination = models.CharField(max_length=500)
    filename = models.CharField(max_length=255, blank=True)
    doc_type = models.CharField(max_length=50)
    is_library = models.BooleanField(
        default=False,
        help_text="True when this run generated a multi-file documentation library "
        "(a folder tree) rather than a single file.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    source_databases = models.JSONField(default=list, blank=True)
    source_docs = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    prompt_used = models.TextField(blank=True)
    agent_output = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Doc Generation Log"
        verbose_name_plural = "Doc Generation Logs"

    def __str__(self) -> str:
        label = f"{self.destination}/ (library)" if self.is_library else self.filename
        return f"{label} — {self.status} ({self.started_at})"
