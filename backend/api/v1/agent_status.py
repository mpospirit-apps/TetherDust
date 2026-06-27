"""Active-agent status endpoint (name + whether it's reachable/authenticated).

Port of the legacy `agent_status_view`: API-key agents are "connected" when a key
is set; Ollama checks the base URL is reachable; Claude Code / Codex check the
gateway `/healthz` and that a credential is present (Codex also verifies the
device-login token isn't expired).
"""

from __future__ import annotations

import datetime
import os

import httpx
from engine.services import AgentService, SystemConfigService, get
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

_API_KEY_TYPES = (
    "openai_platform",
    "claude_console",
    "openai_api",
    "openrouter",
    "codex_api",
    "claude_code_api",
)


class AgentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        agent_config = get(AgentService).get_active()
        if not agent_config:
            return Response({"name": None, "connected": False})

        name = agent_config.name
        agent_type = agent_config.agent_type

        # API-key agents are connected when a key is configured.
        if agent_type in _API_KEY_TYPES:
            return Response({"name": name, "connected": bool(agent_config.api_key)})

        # Ollama runs locally with no key — verify the base URL is reachable.
        if agent_type == "ollama":
            settings = agent_config.settings if isinstance(agent_config.settings, dict) else {}
            base_url = (settings.get("base_url") or "").rstrip("/")
            if not base_url:
                return Response({"name": name, "connected": True})
            try:
                httpx.get(base_url, timeout=3)
                connected = True
            except Exception:
                connected = False
            return Response({"name": name, "connected": connected})

        # Claude Code: gateway reachable AND an OAuth token stored.
        if agent_type == "claude_code":
            db_service_url = get(SystemConfigService).get_value("claude_service_url", "") or ""
            env_url = os.environ.get("CLAUDE_SERVICE_URL", "")
            service_url = (agent_config.service_url or db_service_url or env_url).rstrip("/")
            if not service_url:
                return Response({"name": name, "connected": False})
            try:
                reachable = httpx.get(f"{service_url}/healthz", timeout=3).status_code == 200
            except Exception:
                reachable = False
            connected = reachable and bool(agent_config.auth_token)
            return Response({"name": name, "connected": connected})

        # codex / codex_api via the Codex container: gateway health + auth.json.
        db_service_url = get(SystemConfigService).get_value("codex_service_url", "") or ""
        service_url = (
            agent_config.service_url or db_service_url or os.environ.get("CODEX_SERVICE_URL", "")
        ).rstrip("/")
        if not service_url:
            return Response({"name": name, "connected": False})
        try:
            if httpx.get(f"{service_url}/healthz", timeout=3).status_code != 200:
                return Response({"name": name, "connected": False})
        except Exception:
            return Response({"name": name, "connected": False})

        from engine.agents.gateway import gateway_auth_headers

        try:
            token_resp = httpx.get(
                f"{service_url}/auth/token", timeout=3, headers=gateway_auth_headers()
            )
            token_data = token_resp.json() if token_resp.status_code == 200 else {}
        except Exception:
            token_data = {}

        if not token_data.get("present"):
            return Response({"name": name, "connected": False})

        expires_at = token_data.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.datetime.fromisoformat(expires_at)
                if expiry <= datetime.datetime.now(tz=datetime.UTC):
                    return Response({"name": name, "connected": False})
            except ValueError:
                pass

        return Response({"name": name, "connected": True})
