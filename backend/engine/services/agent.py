"""Agent configuration service.

Holds the behaviour that used to live on ``AgentConfiguration``: enforcing the
single-active-agent invariant, syncing the system prompt to the agent's
container, and decoding the stored ChatGPT credential for display.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
from typing import Any

from ..models.agent import AgentConfiguration
from .registry import get
from .system_config import SystemConfigService

logger = logging.getLogger(__name__)


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


class AgentService:
    """Operations on :class:`AgentConfiguration`."""

    def get_active(self) -> AgentConfiguration | None:
        """Return the currently active agent configuration, or None."""
        return AgentConfiguration.objects.filter(is_active=True).first()

    def save_config(self, agent: AgentConfiguration, **save_kwargs: Any) -> None:
        """Persist an agent, enforcing single-active and syncing its prompt.

        Replaces the old ``AgentConfiguration.save()`` override: when this agent
        is active, every other agent is deactivated first; after saving, the
        system prompt is pushed to the agent's container.
        """
        if agent.is_active:
            AgentConfiguration.objects.filter(is_active=True).exclude(pk=agent.pk).update(
                is_active=False
            )
        agent.save(**save_kwargs)
        self.sync_agents_md(agent)

    def sync_agents_md(self, agent: AgentConfiguration) -> None:
        """Push the system prompt to this agent's container AGENTS.md file."""
        if not agent.system_prompt:
            return
        # Direct API agents run in-process; there is no container to receive
        # AGENTS.md. The system prompt is sent inline per request instead.
        if agent.agent_type in AgentConfiguration.DIRECT_API_AGENT_TYPES:
            return

        import httpx

        # Prefer this agent's own service_url so a non-default container (e.g. the
        # profiled codex-api service) receives its prompt; fall back to the
        # system-wide URL / env var for this agent type when left blank. The
        # fallback must be type-aware so a blank-URL Claude agent never pushes its
        # prompt to the Codex container (and vice versa).
        if agent.agent_type == "claude_code":
            config_key, env_key = "claude_service_url", "CLAUDE_SERVICE_URL"
        elif agent.agent_type == "claude_code_api":
            config_key, env_key = "claude_api_service_url", "CLAUDE_API_SERVICE_URL"
        elif agent.agent_type == "codex_api":
            config_key, env_key = "codex_api_service_url", "CODEX_API_SERVICE_URL"
        else:
            config_key, env_key = "codex_service_url", "CODEX_SERVICE_URL"
        service_url = (
            agent.service_url
            or get(SystemConfigService).get_value(config_key, "")
            or os.environ.get(env_key, "")
        ).rstrip("/")
        if not service_url:
            return
        from engine.agents.gateway import gateway_auth_headers

        try:
            with httpx.Client(timeout=5) as client:
                client.post(
                    f"{service_url}/update-agents-md",
                    json={"content": agent.system_prompt},
                    headers=gateway_auth_headers(),
                ).raise_for_status()
            logger.info("Synced system prompt to %s service", agent.agent_type)
        except Exception:
            logger.warning(
                "Failed to sync system prompt to %s service", agent.agent_type, exc_info=True
            )

    def get_auth_info(self, agent: AgentConfiguration) -> dict[str, object] | None:
        """Decode the stored ChatGPT credential for display.

        Returns a dict with any of ``email``, ``plan``, ``expires_at`` (a
        timezone-aware datetime) parsed from the encrypted ``auth.json``, or None
        when no credential is stored / it can't be decoded. Identity claims come
        from the id_token; expiry from the short-lived access_token. These are
        for display only and are never used for access decisions.
        """
        raw = agent.auth_token
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
