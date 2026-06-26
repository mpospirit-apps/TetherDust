"""MCP server + prompt admin API: CRUD, connectivity test, read-only tool list.

Ports ``management/views/mcp_server.py``. Built-in servers are read-only (their
tools mirror the code). Custom remote/local servers store an encrypted bearer
token + command env; saving or deleting a local (subprocess) server notifies the
local-mcp container to reload.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

import httpx
from django.db.models import Count, QuerySet
from engine.models import MCPServerConfiguration, PromptConfiguration, ToolConfiguration
from engine.services import McpServerService, SystemConfigService, ToolService, get
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta

logger = logging.getLogger(__name__)


def _local_mcp_base_url() -> str:
    return get(SystemConfigService).get_value("local_mcp_base_url", "") or os.getenv(
        "LOCAL_MCP_BASE_URL", "http://local-mcp:8003"
    )


def _notify_local_mcp_reload() -> None:
    """Tell the local-mcp container to reload its server list (best-effort)."""

    def _do_reload() -> None:
        try:
            httpx.post(f"{_local_mcp_base_url().rstrip('/')}/reload", timeout=5.0)
        except Exception:
            pass

    threading.Thread(target=_do_reload, daemon=True).start()


def _parse_json_object(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as err:
        raise serializers.ValidationError(f"Invalid JSON: {err}") from err


class MCPServerSerializer(serializers.ModelSerializer[MCPServerConfiguration]):
    # Encrypted, write-only; blank = keep existing.
    auth_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
        style={"input_type": "password"},
    )
    command_env = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=""
    )
    has_auth_token = serializers.SerializerMethodField()
    has_command_env = serializers.SerializerMethodField()
    is_local = serializers.SerializerMethodField()
    tool_count = serializers.SerializerMethodField()

    class Meta(SerializerMeta):
        model = MCPServerConfiguration
        fields = [
            "id",
            "name",
            "description",
            "url",
            "transport",
            "headers",
            "command",
            "args",
            "auth_token",
            "command_env",
            "is_active",
            "is_builtin",
            "is_local",
            "has_auth_token",
            "has_command_env",
            "tool_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_builtin", "created_at", "updated_at"]

    def get_has_auth_token(self, obj: MCPServerConfiguration) -> bool:
        return bool(obj.auth_token)

    def get_has_command_env(self, obj: MCPServerConfiguration) -> bool:
        return bool(obj.command_env)

    def get_is_local(self, obj: MCPServerConfiguration) -> bool:
        return get(McpServerService).is_local(obj)

    def get_tool_count(self, obj: MCPServerConfiguration) -> int:
        count = getattr(obj, "tool_count", None)
        if count is not None:
            return int(count)
        return ToolConfiguration.objects.filter(mcp_server=obj).count()

    def validate_command_env(self, value: str) -> str:
        if value and not isinstance(_parse_json_object(value), dict):
            raise serializers.ValidationError('Must be a JSON object, e.g. {"KEY": "value"}.')
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        command = (attrs.get("command", getattr(self.instance, "command", "")) or "").strip()
        url = (attrs.get("url", getattr(self.instance, "url", "")) or "").strip()
        if command and url:
            raise serializers.ValidationError(
                "A server cannot have both a command (local subprocess) and a URL "
                "(remote HTTP). Set one or the other."
            )
        if not command and not url:
            raise serializers.ValidationError(
                "Provide either a URL (remote HTTP) or a command (local subprocess)."
            )
        return attrs

    def _apply_secrets(self, instance: MCPServerConfiguration, validated: dict[str, Any]) -> None:
        # Blank token/env means "keep existing"; on create the model field
        # defaults ("" / {}) already cover the unset case, so only write when set.
        token = validated.pop("auth_token", "")
        env_raw = validated.pop("command_env", "")
        if token:
            instance.auth_token = token
        if env_raw:
            instance.command_env = _parse_json_object(env_raw)

    def create(self, validated_data: dict[str, Any]) -> MCPServerConfiguration:
        instance = MCPServerConfiguration(
            **{k: v for k, v in validated_data.items() if k not in ("auth_token", "command_env")}
        )
        self._apply_secrets(instance, validated_data)
        instance.save()
        return instance

    def update(
        self, instance: MCPServerConfiguration, validated_data: dict[str, Any]
    ) -> MCPServerConfiguration:
        secret_keys = ("auth_token", "command_env")
        for attr, value in validated_data.items():
            if attr not in secret_keys:
                setattr(instance, attr, value)
        self._apply_secrets(instance, validated_data)
        instance.save()
        return instance


class MCPServerViewSet(viewsets.ModelViewSet[MCPServerConfiguration]):
    """Staff CRUD for MCP servers, plus a connectivity `test` and a `tools` list."""

    permission_classes = [IsStaffUser]
    serializer_class = MCPServerSerializer

    def get_queryset(self) -> QuerySet[MCPServerConfiguration]:
        return MCPServerConfiguration.objects.annotate(tool_count=Count("tools"))

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if self.get_object().is_builtin:
            return Response(
                {"detail": "Built-in servers cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        response = super().update(request, *args, **kwargs)
        if get(McpServerService).is_local(self.get_object()):
            _notify_local_mcp_reload()
        return response

    def perform_create(self, serializer: Any) -> None:
        instance = serializer.save()
        if get(McpServerService).is_local(instance):
            _notify_local_mcp_reload()

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        obj = self.get_object()
        if obj.is_builtin:
            return Response(
                {"detail": "Built-in servers cannot be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        was_local = get(McpServerService).is_local(obj)
        obj.delete()
        if was_local:
            _notify_local_mcp_reload()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def tools(self, request: Request, pk: str | None = None) -> Response:
        """Read-only tool list for this server."""
        server = self.get_object()
        tool_service = get(ToolService)
        return Response(
            {
                "results": [
                    {
                        "id": tool.id,
                        "tool_name": tool.tool_name,
                        "display_name": tool.display_name,
                        "category": tool.category,
                        "category_label": tool_service.category_label(tool),
                        "is_enabled": tool.is_enabled,
                        "description": tool.description,
                    }
                    for tool in ToolConfiguration.objects.filter(mcp_server=server)
                ]
            }
        )

    @action(detail=True, methods=["post"])
    def test(self, request: Request, pk: str | None = None) -> Response:
        """Probe a remote/local MCP server with initialize + tools/list."""
        server = self.get_object()
        return Response(_probe_server(server))


def _parse_mcp_body(resp: httpx.Response) -> dict[str, Any]:
    ctype = resp.headers.get("content-type", "").lower()
    text = resp.text or ""
    if "text/event-stream" in ctype:
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[len("data:") :].strip()
                if data and data != "[DONE]":
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(parsed, dict):
                        raise ValueError("Expected a JSON object")
                    return parsed
        raise ValueError("SSE stream contained no JSON data frame")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _probe_server(server: MCPServerConfiguration) -> dict[str, Any]:
    if server.is_builtin:
        return {
            "ok": False,
            "error": "Built-in server is not testable here — it is served in-process "
            "by the MCP container.",
        }

    is_local = get(McpServerService).is_local(server)
    if is_local:
        url = f"{_local_mcp_base_url().rstrip('/')}/mcp/{server.pk}/"
    else:
        url = (server.url or "").strip()
    if not url:
        return {"ok": False, "error": "Server has no URL configured."}

    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    token = ""
    if not is_local:
        for k, v in (server.headers or {}).items():
            headers[str(k)] = str(v)
        token = server.auth_token
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"

    init_req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "tetherdust-admin-test", "version": "1.0"},
        },
    }
    list_req = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}}

    result: dict[str, Any] = {
        "url": url,
        "transport": "streamable-http" if is_local else (server.transport or "streamable-http"),
        "has_auth_token": bool(token),
        "header_keys": sorted(k for k in headers if k.lower() not in ("content-type", "accept")),
    }

    http_timeout = 120.0 if is_local else 15.0
    try:
        start = time.monotonic()
        with httpx.Client(timeout=http_timeout, follow_redirects=True) as client:
            init_resp = client.post(url, json=init_req, headers=headers)
            init_info: dict[str, Any] = {
                "status_code": init_resp.status_code,
                "elapsed_ms": int((time.monotonic() - start) * 1000),
                "content_type": init_resp.headers.get("content-type", ""),
            }
            result["initialize"] = init_info
            if init_resp.status_code >= 400:
                result["ok"] = False
                result["error"] = f"initialize returned HTTP {init_resp.status_code}"
                init_info["body_preview"] = (init_resp.text or "")[:500]
                return result

            try:
                init_payload = _parse_mcp_body(init_resp)
            except (ValueError, json.JSONDecodeError) as exc:
                result["ok"] = False
                result["error"] = f"initialize body was not valid MCP JSON-RPC: {exc}"
                init_info["body_preview"] = (init_resp.text or "")[:500]
                return result

            if "error" in init_payload:
                result["ok"] = False
                result["error"] = f"initialize error: {init_payload['error']}"
                return result

            server_info = (init_payload.get("result") or {}).get("serverInfo") or {}
            init_info["protocol_version"] = init_payload.get("result", {}).get("protocolVersion")
            init_info["server_name"] = server_info.get("name")
            init_info["server_version"] = server_info.get("version")

            session_id = init_resp.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            try:
                client.post(
                    url,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    headers=headers,
                )
            except httpx.HTTPError:
                pass

            list_start = time.monotonic()
            list_resp = client.post(url, json=list_req, headers=headers)
            list_info: dict[str, Any] = {
                "status_code": list_resp.status_code,
                "elapsed_ms": int((time.monotonic() - list_start) * 1000),
            }
            result["tools_list"] = list_info
            if list_resp.status_code >= 400:
                result["ok"] = False
                result["error"] = f"tools/list returned HTTP {list_resp.status_code}"
                list_info["body_preview"] = (list_resp.text or "")[:500]
                return result

            try:
                list_payload = _parse_mcp_body(list_resp)
            except (ValueError, json.JSONDecodeError) as exc:
                result["ok"] = False
                result["error"] = f"tools/list body was not valid MCP JSON-RPC: {exc}"
                list_info["body_preview"] = (list_resp.text or "")[:500]
                return result

            if "error" in list_payload:
                result["ok"] = False
                result["error"] = f"tools/list error: {list_payload['error']}"
                return result

            tools = (list_payload.get("result") or {}).get("tools") or []
            list_info["count"] = len(tools)
            list_info["tools"] = [
                {"name": t.get("name", ""), "description": (t.get("description") or "")[:200]}
                for t in tools[:50]
            ]
            result["ok"] = True
            return result
    except httpx.ConnectError as exc:
        return {**result, "ok": False, "error": f"Connection failed: {exc}"}
    except httpx.TimeoutException:
        return {**result, "ok": False, "error": f"Timed out after {int(http_timeout)}s"}
    except httpx.HTTPError as exc:
        return {**result, "ok": False, "error": f"HTTP error: {exc}"}
    except Exception as exc:
        logger.exception("MCP test failed for server %s", server.pk)
        return {**result, "ok": False, "error": f"Unexpected error: {exc}"}


class PromptSerializer(serializers.ModelSerializer[PromptConfiguration]):
    class Meta(SerializerMeta):
        model = PromptConfiguration
        fields = [
            "id",
            "mcp_server",
            "prompt_name",
            "display_name",
            "content",
            "is_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PromptViewSet(viewsets.ModelViewSet[PromptConfiguration]):
    """Staff CRUD for MCP prompt templates, filterable by ``?mcp_server=``."""

    permission_classes = [IsStaffUser]
    serializer_class = PromptSerializer

    def get_queryset(self) -> QuerySet[PromptConfiguration]:
        qs = PromptConfiguration.objects.all()
        server_id = self.request.query_params.get("mcp_server")
        if server_id:
            qs = qs.filter(mcp_server_id=server_id)
        return qs

    @action(detail=True, methods=["post"])
    def toggle(self, request: Request, pk: str | None = None) -> Response:
        prompt = self.get_object()
        prompt.is_enabled = not prompt.is_enabled
        prompt.save(update_fields=["is_enabled"])
        return Response(self.get_serializer(prompt).data)
