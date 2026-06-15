"""MCP server, tool, and prompt CRUD + connectivity test."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.models import (
    MCPServerConfiguration,
    PromptConfiguration,
    ToolConfiguration,
)
from django.conf import settings
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from console.views._helpers import staff_required

from ..forms import (
    MCPServerConfigurationForm,
    PromptConfigurationForm,
)
from ._helpers import logger


@staff_required
def mcp_server_list_view(request: HttpRequest) -> HttpResponse:
    servers = MCPServerConfiguration.objects.annotate(tool_count=Count("tools"))
    return render(
        request,
        "console/mcp_servers/list.html",
        {
            "servers": servers,
            "section": "mcp_servers",
        },
    )


@staff_required
def mcp_server_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    server = get_object_or_404(MCPServerConfiguration, pk=pk)
    tools = ToolConfiguration.objects.filter(mcp_server=server)
    prompts = PromptConfiguration.objects.filter(mcp_server=server)
    return render(
        request,
        "console/mcp_servers/detail.html",
        {
            "server": server,
            "tools": tools,
            "prompts": prompts,
            "section": "mcp_servers",
        },
    )


def _notify_local_mcp_reload() -> None:
    """Tell the local-mcp container to reload its server list. Silently ignored on failure."""
    import threading

    def _do_reload() -> None:
        try:
            import httpx
            from core.models import SystemConfiguration as SysConf

            base = SysConf.get_value("local_mcp_base_url", "") or os.getenv(
                "LOCAL_MCP_BASE_URL", "http://local-mcp:8003"
            )
            httpx.post(f"{base.rstrip('/')}/reload", timeout=5.0)
        except Exception:
            pass

    threading.Thread(target=_do_reload, daemon=True).start()


@staff_required
def mcp_server_form_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    instance = get_object_or_404(MCPServerConfiguration, pk=pk) if pk else None
    if instance and instance.is_builtin:
        return redirect("console:mcp_server_detail", pk=instance.pk)
    if request.method == "POST":
        form = MCPServerConfigurationForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            assert isinstance(saved, MCPServerConfiguration)
            if saved.is_local:
                _notify_local_mcp_reload()
            return redirect("console:mcp_server_list")
    else:
        form = MCPServerConfigurationForm(instance=instance)
    return render(
        request,
        "console/mcp_servers/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "mcp_servers",
        },
    )


@staff_required
@require_POST
def mcp_server_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(MCPServerConfiguration, pk=pk)
    if obj.is_builtin:
        return redirect("console:mcp_server_detail", pk=obj.pk)
    was_local = obj.is_local
    obj.delete()
    if was_local:
        _notify_local_mcp_reload()
    return redirect("console:mcp_server_list")


@staff_required
@require_POST
def mcp_server_test_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Probe a remote MCP server with initialize + tools/list and report back."""
    import time
    import uuid

    import httpx

    server = get_object_or_404(MCPServerConfiguration, pk=pk)
    if server.is_builtin:
        return JsonResponse(
            {
                "ok": False,
                "error": "Built-in server is not testable here — it is served in-process by the MCP container.",  # noqa: E501
            },
            status=400,
        )

    if server.is_local:
        from core.models import SystemConfiguration as SysConf

        base = SysConf.get_value("local_mcp_base_url", "") or os.getenv(
            "LOCAL_MCP_BASE_URL", "http://local-mcp:8003"
        )
        url = f"{base.rstrip('/')}/mcp/{server.pk}/"
    else:
        url = (server.url or "").strip()

    if not url:
        return JsonResponse({"ok": False, "error": "Server has no URL configured."}, status=400)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if not server.is_local:
        for k, v in (server.headers or {}).items():
            headers[str(k)] = str(v)
        token = server.auth_token
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
    else:
        token = ""

    def _parse_body(resp: httpx.Response) -> dict[str, Any]:
        ctype = resp.headers.get("content-type", "").lower()
        text = resp.text or ""
        if "text/event-stream" in ctype:
            for line in text.splitlines():
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                    if data and data != "[DONE]":
                        try:
                            parsed = json.loads(data)
                            if not isinstance(parsed, dict):
                                raise ValueError("Expected a JSON object")
                            return parsed
                        except json.JSONDecodeError:
                            continue
            raise ValueError("SSE stream contained no JSON data frame")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object")
        return parsed

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
    list_req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/list",
        "params": {},
    }

    result: dict[str, Any] = {
        "url": url,
        "transport": "streamable-http"
        if server.is_local
        else (server.transport or "streamable-http"),
        "has_auth_token": bool(token),
        "header_keys": sorted(k for k in headers if k.lower() not in ("content-type", "accept")),
    }

    http_timeout = 120.0 if server.is_local else 15.0
    try:
        start = time.monotonic()
        with httpx.Client(timeout=http_timeout, follow_redirects=True) as client:
            init_resp = client.post(url, json=init_req, headers=headers)
            init_elapsed = int((time.monotonic() - start) * 1000)
            result["initialize"] = {
                "status_code": init_resp.status_code,
                "elapsed_ms": init_elapsed,
                "content_type": init_resp.headers.get("content-type", ""),
            }
            if init_resp.status_code >= 400:
                result["ok"] = False
                result["error"] = f"initialize returned HTTP {init_resp.status_code}"
                result["initialize"]["body_preview"] = (init_resp.text or "")[:500]
                return JsonResponse(result, status=200)

            try:
                init_payload = _parse_body(init_resp)
            except (ValueError, json.JSONDecodeError) as exc:
                result["ok"] = False
                result["error"] = f"initialize body was not valid MCP JSON-RPC: {exc}"
                result["initialize"]["body_preview"] = (init_resp.text or "")[:500]
                return JsonResponse(result, status=200)

            if "error" in init_payload:
                result["ok"] = False
                result["error"] = f"initialize error: {init_payload['error']}"
                return JsonResponse(result, status=200)

            server_info = (init_payload.get("result") or {}).get("serverInfo") or {}
            result["initialize"]["protocol_version"] = init_payload.get("result", {}).get(
                "protocolVersion"
            )
            result["initialize"]["server_name"] = server_info.get("name")
            result["initialize"]["server_version"] = server_info.get("version")

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
            list_elapsed = int((time.monotonic() - list_start) * 1000)
            tools_list: dict[str, Any] = {
                "status_code": list_resp.status_code,
                "elapsed_ms": list_elapsed,
            }
            result["tools_list"] = tools_list
            if list_resp.status_code >= 400:
                result["ok"] = False
                result["error"] = f"tools/list returned HTTP {list_resp.status_code}"
                result["tools_list"]["body_preview"] = (list_resp.text or "")[:500]
                return JsonResponse(result, status=200)

            try:
                list_payload = _parse_body(list_resp)
            except (ValueError, json.JSONDecodeError) as exc:
                result["ok"] = False
                result["error"] = f"tools/list body was not valid MCP JSON-RPC: {exc}"
                result["tools_list"]["body_preview"] = (list_resp.text or "")[:500]
                return JsonResponse(result, status=200)

            if "error" in list_payload:
                result["ok"] = False
                result["error"] = f"tools/list error: {list_payload['error']}"
                return JsonResponse(result, status=200)

            tools = (list_payload.get("result") or {}).get("tools") or []
            result["tools_list"]["count"] = len(tools)
            result["tools_list"]["tools"] = [
                {
                    "name": t.get("name", ""),
                    "description": (t.get("description") or "")[:200],
                }
                for t in tools[:50]
            ]
            result["ok"] = True
            return JsonResponse(result, status=200)
    except httpx.ConnectError as exc:
        return JsonResponse(
            {**result, "ok": False, "error": f"Connection failed: {exc}"}, status=200
        )
    except httpx.TimeoutException:
        return JsonResponse({**result, "ok": False, "error": "Timed out after 15s"}, status=200)
    except httpx.HTTPError as exc:
        return JsonResponse({**result, "ok": False, "error": f"HTTP error: {exc}"}, status=200)
    except Exception as exc:
        logger.exception("MCP test failed for server %s", server.pk)
        return JsonResponse(
            {**result, "ok": False, "error": f"Unexpected error: {exc}"}, status=200
        )


def _builtin_tool_meta(tool_name: str) -> tuple[str | None, str | None]:
    """Return ``(input_schema_json, description)`` for a built-in tool, derived
    from its function exactly as FastMCP exposes them to the agent (schema from the
    signature, description from the docstring). ``(None, None)`` if unresolvable.
    """
    import importlib
    import sys

    try:
        from mcp.server.fastmcp.tools import Tool

        # tdmcp lives at the repository root (…/tdmcp),
        # which isn't on the web app's path by default.
        repo_root = str(Path(settings.BASE_DIR).parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        module = importlib.import_module(f"tdmcp.tools.{tool_name}")
        fn = getattr(module, tool_name)
        tool = Tool.from_function(fn)
        return json.dumps(tool.parameters, indent=2), (tool.description or "")
    except Exception:
        logger.debug("Could not derive metadata for built-in tool %s", tool_name, exc_info=True)
        return None, None


@staff_required
def tool_detail_view(request: HttpRequest, server_pk: int, pk: int) -> HttpResponse:
    """Read-only view of a tool. Built-in tools are a fixed mirror of the code, so
    there is nothing to edit, add, or delete — the agent-facing description, input
    schema, and handler code are shown live from the function/module."""
    server = get_object_or_404(MCPServerConfiguration, pk=server_pk)
    tool = get_object_or_404(ToolConfiguration, pk=pk, mcp_server=server)

    handler_source = ""
    input_schema_display = json.dumps(tool.input_schema or {}, indent=2)
    tool_description = tool.description
    if server.is_builtin:
        schema_json, agent_description = _builtin_tool_meta(tool.tool_name)
        if schema_json:
            input_schema_display = schema_json
        if agent_description:
            tool_description = agent_description
        handler_path = Path(settings.BASE_DIR).parent / "tdmcp" / "tools" / f"{tool.tool_name}.py"
        if handler_path.exists():
            handler_source = handler_path.read_text(encoding="utf-8")

    return render(
        request,
        "console/tools/detail.html",
        {
            "tool": tool,
            "server": server,
            "handler_source": handler_source,
            "input_schema_display": input_schema_display,
            "tool_description": tool_description,
            "section": "mcp_servers",
        },
    )


@staff_required
def prompt_form_view(request: HttpRequest, server_pk: int, pk: int | None = None) -> HttpResponse:
    server = get_object_or_404(MCPServerConfiguration, pk=server_pk)
    instance = get_object_or_404(PromptConfiguration, pk=pk, mcp_server=server) if pk else None

    if request.method == "POST":
        form = PromptConfigurationForm(request.POST, instance=instance)
        if form.is_valid():
            prompt = form.save(commit=False)
            prompt.mcp_server = server
            prompt.save()
            return redirect("console:mcp_server_detail", pk=server.pk)
    else:
        form = PromptConfigurationForm(instance=instance)

    return render(
        request,
        "console/prompts/form.html",
        {
            "form": form,
            "instance": instance,
            "server": server,
            "section": "mcp_servers",
        },
    )


@staff_required
@require_POST
def prompt_toggle_view(request: HttpRequest, server_pk: int, pk: int) -> HttpResponse:
    """Toggle prompt enabled/disabled via HTMX."""
    obj = get_object_or_404(PromptConfiguration, pk=pk, mcp_server_id=server_pk)
    obj.is_enabled = not obj.is_enabled
    obj.save(update_fields=["is_enabled"])
    status = "enabled" if obj.is_enabled else "disabled"
    css = "badge-success" if obj.is_enabled else "badge-muted"
    return HttpResponse(f'<span class="badge {css}">{status.upper()}</span>')


@staff_required
@require_POST
def prompt_delete_view(request: HttpRequest, server_pk: int, pk: int) -> HttpResponse:
    obj = get_object_or_404(PromptConfiguration, pk=pk, mcp_server_id=server_pk)
    obj.delete()
    return redirect("console:mcp_server_detail", pk=server_pk)
