"""Agent configuration admin API: CRUD + activate + type metadata.

Per-type auth, mirroring the legacy agent form: API-key agents (codex_api /
claude_code_api / direct-API types) store an encrypted `api_key`; `claude_code`
stores a pasted OAuth token in `auth_token`; `model` / `base_url` /
`reasoning_effort` live in `settings`. `agent_type` is fixed after creation.
Single-active + system-prompt sync are handled by `AgentService.save_config`.

Codex auth-token agents can sign in via the OAuth **device-code** flow: the
`device-login` actions proxy the Codex gateway (`/auth/device/{start,status}`)
and persist the resulting `auth.json` on completion.

The `default-prompt` action seeds the System Prompt textarea from the baked-in
container default (`docker/codex/AGENTS.md` / `docker/claude/CLAUDE.md`) so a
blank-prompt agent shows the prompt it effectively uses (ports the legacy form
pre-fill); display only, persisted only if the form is saved.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings
from engine.agents.gateway import gateway_auth_headers
from engine.models import AgentConfiguration
from engine.services import AgentService, SystemConfigService, get
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


def _resolve_codex_url(config: AgentConfiguration) -> str:
    """Resolve the Codex gateway URL (per-config override → system config → env)."""
    config_url = config.service_url or ""
    db_url = get(SystemConfigService).get_value("codex_service_url", "") or ""
    return (config_url or db_url or os.environ.get("CODEX_SERVICE_URL", "")).rstrip("/")


def _default_system_prompt(agent_type: str) -> str:
    """Baked-in default prompt for an agent type (its container's AGENTS.md/CLAUDE.md).

    Claude Code seeds from `docker/claude/CLAUDE.md`; every other CLI / Direct-API
    type from `docker/codex/AGENTS.md`. These repo files are copied into the
    backend image via the Dockerfile, resolving to `/app/docker/...`. Missing
    file → "" (the textarea simply stays blank, as in the legacy form).
    """
    docker_dir = Path(settings.BASE_DIR).parent / "docker"
    if agent_type in ("claude_code", "claude_code_api"):
        path = docker_dir / "claude" / "CLAUDE.md"
    else:
        path = docker_dir / "codex" / "AGENTS.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


_API_KEY_TYPES = {"codex_api", "claude_code_api"} | AgentConfiguration.DIRECT_API_AGENT_TYPES
_EXTRA_FIELDS = ("api_key", "oauth_token", "model", "base_url", "reasoning_effort")
_REASONING_EFFORT = [
    {"value": "", "label": "Default"},
    {"value": "minimal", "label": "Minimal"},
    {"value": "low", "label": "Low"},
    {"value": "medium", "label": "Medium"},
    {"value": "high", "label": "High"},
    {"value": "xhigh", "label": "Extra high"},
]


class AgentSerializer(serializers.ModelSerializer[AgentConfiguration]):
    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
        style={"input_type": "password"},
    )
    oauth_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
        style={"input_type": "password"},
    )
    model = serializers.CharField(required=False, allow_blank=True, default="")
    base_url = serializers.CharField(required=False, allow_blank=True, default="")
    reasoning_effort = serializers.CharField(required=False, allow_blank=True, default="")
    agent_type_display = serializers.CharField(source="get_agent_type_display", read_only=True)
    has_api_key = serializers.SerializerMethodField()
    has_auth_token = serializers.SerializerMethodField()
    auth_info = serializers.SerializerMethodField()

    class Meta(SerializerMeta):
        model = AgentConfiguration
        fields = [
            "id",
            "name",
            "agent_type",
            "agent_type_display",
            "system_prompt",
            "service_url",
            "is_active",
            "api_key",
            "oauth_token",
            "model",
            "base_url",
            "reasoning_effort",
            "has_api_key",
            "has_auth_token",
            "auth_info",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]

    def get_has_api_key(self, obj: AgentConfiguration) -> bool:
        return bool(obj.api_key)

    def get_has_auth_token(self, obj: AgentConfiguration) -> bool:
        return bool(obj.auth_token)

    def get_auth_info(self, obj: AgentConfiguration) -> dict[str, Any] | None:
        """Decoded ChatGPT credential (email/plan/expiry) for Codex device-login.

        Only Codex stores a JSON `auth.json`; other auth-token types hold an
        opaque OAuth token with nothing to decode.
        """
        if obj.agent_type != "codex":
            return None
        info = get(AgentService).get_auth_info(obj)
        if not info:
            return None
        out: dict[str, Any] = dict(info)
        expires = out.get("expires_at")
        if isinstance(expires, datetime.datetime):
            out["expires_at"] = expires.isoformat()
        return out

    def to_representation(self, instance: Any) -> Any:
        data = super().to_representation(instance)
        settings = instance.settings if isinstance(instance.settings, dict) else {}
        data["model"] = settings.get("model", "")
        data["base_url"] = settings.get("base_url", "")
        data["reasoning_effort"] = settings.get("reasoning_effort", "")
        return data

    def validate(self, attrs: Any) -> Any:
        agent_type = self.instance.agent_type if self.instance else attrs.get("agent_type")
        if agent_type in _API_KEY_TYPES and not attrs.get("api_key"):
            existing = self.instance.api_key if self.instance else ""
            if not existing:
                raise serializers.ValidationError(
                    {"api_key": "An API key is required for this agent type."}
                )
        return attrs

    def _apply_extra(self, instance: AgentConfiguration, extra: dict[str, Any]) -> None:
        agent_type = instance.agent_type
        settings = instance.settings if isinstance(instance.settings, dict) else {}
        if agent_type in AgentConfiguration.DIRECT_API_AGENT_TYPES:
            settings["model"] = (extra.get("model") or "").strip()
            settings["base_url"] = (extra.get("base_url") or "").strip().rstrip("/")
        elif agent_type in ("codex", "codex_api"):
            settings["model"] = (extra.get("model") or "").strip()
            settings["reasoning_effort"] = (extra.get("reasoning_effort") or "").strip()
        elif agent_type in ("claude_code", "claude_code_api"):
            settings["model"] = (extra.get("model") or "").strip()
        instance.settings = settings

        api_key = extra.get("api_key") or ""
        if agent_type in _API_KEY_TYPES and api_key:
            instance.api_key = api_key
        oauth_token = extra.get("oauth_token") or ""
        if agent_type == "claude_code" and oauth_token:
            instance.auth_token = oauth_token

    def create(self, validated_data: Any) -> AgentConfiguration:
        extra = {key: validated_data.pop(key, "") for key in _EXTRA_FIELDS}
        instance = AgentConfiguration(**validated_data)
        self._apply_extra(instance, extra)
        get(AgentService).save_config(instance)
        return instance

    def update(self, instance: AgentConfiguration, validated_data: Any) -> AgentConfiguration:
        extra = {key: validated_data.pop(key, "") for key in _EXTRA_FIELDS}
        validated_data.pop("agent_type", None)  # fixed after creation
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        self._apply_extra(instance, extra)
        get(AgentService).save_config(instance)
        return instance


class AgentViewSet(viewsets.ModelViewSet[AgentConfiguration]):
    permission_classes = [IsStaffUser]
    queryset = AgentConfiguration.objects.all()
    serializer_class = AgentSerializer

    @action(detail=False, methods=["get"])
    def types(self, request: Request) -> Response:
        """Agent-type categories + per-type auth metadata for the create flow."""
        names = dict(AgentConfiguration.AGENT_TYPE_CHOICES)
        categories = [
            {
                "title": title,
                "types": [{"value": k, "label": names[k]} for k in keys if k in names],
            }
            for title, keys in AgentConfiguration.AGENT_TYPE_CATEGORIES
        ]
        return Response(
            {
                "categories": categories,
                "direct_api_types": sorted(AgentConfiguration.DIRECT_API_AGENT_TYPES),
                "api_key_types": sorted(_API_KEY_TYPES),
                "auth_token_types": sorted(AgentConfiguration.AUTH_TOKEN_AGENT_TYPES),
                "reasoning_effort_choices": _REASONING_EFFORT,
            }
        )

    @action(detail=False, methods=["get"], url_path="default-prompt")
    def default_prompt(self, request: Request) -> Response:
        """Default system prompt for `?agent_type=` — the container AGENTS.md/CLAUDE.md.

        The SPA seeds the System Prompt textarea from this when an agent's prompt
        is blank, so the admin sees and can edit the prompt the agent effectively
        uses. Display only — persisted only if the form is saved.
        """
        agent_type = request.query_params.get("agent_type", "")
        return Response({"system_prompt": _default_system_prompt(agent_type)})

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        agent = self.get_object()
        agent.is_active = True
        get(AgentService).save_config(agent)
        return Response(self.get_serializer(agent).data)

    @action(detail=True, methods=["post"], url_path="device-login")
    def device_login_start(self, request: Request, pk: str | None = None) -> Response:
        """Begin a Codex device-code login by proxying the Codex gateway.

        Returns `{login_id, verification_url, user_code}`; the SPA shows the URL
        + code and polls `device_login_status` until the user approves.
        """
        agent = self.get_object()
        codex_url = _resolve_codex_url(agent)
        if not codex_url:
            return Response(
                {"detail": "Codex service URL is not configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            # Codex blocks up to ~60s capturing the device prompt before replying.
            with httpx.Client(timeout=75) as client:
                resp = client.post(f"{codex_url}/auth/device/start", headers=gateway_auth_headers())
        except httpx.HTTPError:
            return Response(
                {"detail": "Unable to reach the Codex service."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if resp.status_code != 200:
            detail = None
            try:
                detail = resp.json().get("error")
            except Exception:
                pass
            return Response(
                {"detail": detail or "Could not start sign-in."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(resp.json())

    @action(detail=True, methods=["get"], url_path="device-login/(?P<login_id>[^/]+)")
    def device_login_status(
        self, request: Request, pk: str | None = None, login_id: str = ""
    ) -> Response:
        """Poll a Codex device login; persist the credential on completion."""
        agent = self.get_object()
        codex_url = _resolve_codex_url(agent)
        if not codex_url:
            return Response(
                {"detail": "Codex service URL is not configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{codex_url}/auth/device/status/{login_id}",
                    headers=gateway_auth_headers(),
                )
        except httpx.HTTPError:
            return Response(
                {"detail": "Unable to reach the Codex service."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if resp.status_code == 404:
            return Response({"status": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        data = resp.json()
        state = data.get("status")
        if state == "complete":
            token = data.get("auth_token", "")
            if token:
                agent.auth_token = token
                get(AgentService).save_config(agent)
            return Response({"status": "complete"})
        if state == "error":
            return Response({"status": "error", "error": data.get("error", "")})
        return Response(
            {
                "status": state or "pending",
                "verification_url": data.get("verification_url"),
                "user_code": data.get("user_code"),
            }
        )

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        if instance.is_active:
            return Response(
                {"detail": "Switch to another agent before deleting the active one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
