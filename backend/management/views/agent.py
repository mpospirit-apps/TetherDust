"""Agent configuration CRUD + activation."""

import os
from pathlib import Path

import httpx
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from engine.agents.gateway import gateway_auth_headers as _gateway_auth_headers
from engine.models import AgentConfiguration
from engine.services import AgentService, SystemConfigService, get

from management.views._helpers import staff_required

from ..forms import AgentConfigurationForm


def _default_system_prompt_path(agent_type: str | None) -> Path:
    """Path to the default system prompt for a new agent of this type.

    Claude Code seeds from its own CLAUDE.md; every other CLI agent seeds from
    the Codex AGENTS.md.
    """
    docker_dir = Path(settings.BASE_DIR).parent / "docker"
    if agent_type in ("claude_code", "claude_code_api"):
        return docker_dir / "claude" / "CLAUDE.md"
    return docker_dir / "codex" / "AGENTS.md"


def _resolve_codex_url(config: object = None) -> str:
    """Resolve the Codex service URL (per-config override → system config → env)."""
    config_url = (getattr(config, "service_url", "") or "") if config else ""
    db_url = get(SystemConfigService).get_value("codex_service_url", "") or ""
    return (config_url or db_url or os.environ.get("CODEX_SERVICE_URL", "")).rstrip("/")


async def _resolve_codex_url_async(config: object = None) -> str:
    """Async version of _resolve_codex_url for use inside async views."""
    from asgiref.sync import sync_to_async

    config_url = (getattr(config, "service_url", "") or "") if config else ""
    db_url = await sync_to_async(get(SystemConfigService).get_value)("codex_service_url", "") or ""
    return (config_url or db_url or os.environ.get("CODEX_SERVICE_URL", "")).rstrip("/")


@staff_required
def agent_list_view(request: HttpRequest) -> HttpResponse:
    agents = AgentConfiguration.objects.all()
    return render(
        request,
        "management/agents/list.html",
        {
            "agents": agents,
            "section": "agents",
        },
    )


@staff_required
def agent_type_picker_view(request: HttpRequest) -> HttpResponse:
    """Step 1 of Add Agent: choose an agent type, grouped by integration category."""
    names = dict(AgentConfiguration.AGENT_TYPE_CHOICES)
    categories = [
        {
            "title": title,
            "types": [(key, names[key]) for key in keys if key in names],
        }
        for title, keys in AgentConfiguration.AGENT_TYPE_CATEGORIES
    ]
    return render(
        request,
        "management/agents/type_picker.html",
        {
            "agent_categories": [c for c in categories if c["types"]],
            "section": "agents",
        },
    )


@staff_required
def agent_form_view(
    request: HttpRequest, pk: str | None = None, agent_type: str | None = None
) -> HttpResponse:
    instance = get_object_or_404(AgentConfiguration, pk=pk) if pk else None

    valid_types = {key for key, _ in AgentConfiguration.AGENT_TYPE_CHOICES}
    if agent_type and agent_type not in valid_types:
        return redirect("management:agent_add")

    if request.method == "POST":
        form = AgentConfigurationForm(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            # API-key agents store their key encrypted. A blank field on edit
            # keeps the existing key (PasswordInput never re-renders it).
            api_key = form.cleaned_data.get("api_key")
            api_key_types = {
                "codex_api",
                "claude_code_api",
            } | AgentConfiguration.DIRECT_API_AGENT_TYPES
            if obj.agent_type in api_key_types and api_key:
                obj.api_key = api_key
            # Claude Code stores a subscription OAuth token (pasted, not a device
            # flow). A blank field on edit keeps the existing token.
            oauth_token = form.cleaned_data.get("oauth_token")
            if obj.agent_type == "claude_code" and oauth_token:
                obj.auth_token = oauth_token
            # Direct API agents store model / base_url in the settings JSON.
            if obj.agent_type in AgentConfiguration.DIRECT_API_AGENT_TYPES:
                agent_settings = obj.settings if isinstance(obj.settings, dict) else {}
                agent_settings["model"] = form.cleaned_data.get("model", "").strip()
                agent_settings["base_url"] = (
                    form.cleaned_data.get("base_url", "").strip().rstrip("/")
                )
                obj.settings = agent_settings
            # Codex agents store an optional model + reasoning effort override.
            elif obj.agent_type in ("codex", "codex_api"):
                agent_settings = obj.settings if isinstance(obj.settings, dict) else {}
                agent_settings["model"] = form.cleaned_data.get("model", "").strip()
                agent_settings["reasoning_effort"] = form.cleaned_data.get(
                    "reasoning_effort", ""
                ).strip()
                obj.settings = agent_settings
            # Claude Code stores an optional model override (no reasoning effort).
            elif obj.agent_type in ("claude_code", "claude_code_api"):
                agent_settings = obj.settings if isinstance(obj.settings, dict) else {}
                agent_settings["model"] = form.cleaned_data.get("model", "").strip()
                obj.settings = agent_settings
            get(AgentService).save_config(obj)
            return redirect("management:agent_list")
    else:
        initial = {"agent_type": agent_type} if agent_type else {}
        if agent_type and not instance:
            agents_md = _default_system_prompt_path(agent_type)
            if agents_md.exists():
                initial["system_prompt"] = agents_md.read_text(encoding="utf-8")
            # Pre-fill the provider base URL for each direct-API preset so the
            # admin doesn't have to look it up. The generic "openai_api" (Custom)
            # type is intentionally left blank for the admin to fill in.
            preset_base_urls = {
                "openai_platform": "https://api.openai.com/v1",
                "claude_console": "https://api.anthropic.com/v1",
                "ollama": "http://ollama:11434/v1",
                "openrouter": "https://openrouter.ai/api/v1",
            }
            if agent_type in preset_base_urls:
                initial["base_url"] = preset_base_urls[agent_type]
        if instance and not instance.system_prompt:
            agents_md = _default_system_prompt_path(instance.agent_type)
            if agents_md.exists():
                instance.system_prompt = agents_md.read_text(encoding="utf-8")
        form = AgentConfigurationForm(instance=instance, initial=initial)

    # The agent type is chosen once (via the type picker) and fixed thereafter.
    # Resolve it from the URL on create or from the instance on edit so the form
    # can show it read-only instead of as an editable dropdown.
    display_type_key = agent_type or (instance.agent_type if instance else None)
    agent_type_display = (
        dict(AgentConfiguration.AGENT_TYPE_CHOICES).get(display_type_key)
        if display_type_key
        else None
    )

    # Per-preset model placeholder so the field's example matches the provider
    # (a generic "gpt-4o" would mislead for Claude Console / Ollama / OpenRouter).
    model_placeholders = {
        "openai_platform": "gpt-4o",
        "claude_console": "claude-haiku-4-5-20251001",
        "openrouter": "anthropic/claude-sonnet-4-5",
        "ollama": "llama3.1",
    }
    if display_type_key in model_placeholders:
        form.fields["model"].widget.attrs["placeholder"] = model_placeholders[display_type_key]

    direct_types = AgentConfiguration.DIRECT_API_AGENT_TYPES
    is_direct_api = (agent_type in direct_types) or bool(
        instance and instance.agent_type in direct_types
    )

    # For a saved Codex (auth-token) agent, decode the stored credential so the
    # form can show who is signed in instead of a bare "Sign in" button.
    auth_info = None
    if instance and instance.agent_type == "codex":
        auth_info = get(AgentService).get_auth_info(instance)

    # Whether a Claude Code OAuth token is already stored (so the form can show
    # "leave blank to keep" instead of implying none is set).
    claude_token_set = bool(
        instance and instance.agent_type == "claude_code" and instance.auth_token
    )

    return render(
        request,
        "management/agents/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "agents",
            "agent_type_key": agent_type,
            "display_type_key": display_type_key,
            "agent_type_display": agent_type_display,
            "is_new_with_type": bool(agent_type and not instance),
            "is_direct_api": is_direct_api,
            "auth_info": auth_info,
            "claude_token_set": claude_token_set,
        },
    )


@staff_required
@require_POST
def agent_delete_view(request: HttpRequest, pk: str) -> HttpResponse:
    obj = get_object_or_404(AgentConfiguration, pk=pk)
    if obj.is_active:
        return redirect("management:agent_list")
    obj.delete()
    return redirect("management:agent_list")


@staff_required
@require_POST
async def agent_device_login_start(request: HttpRequest, pk: str) -> HttpResponse:
    """Begin an in-app device-code login by proxying to the Codex service."""
    from django.shortcuts import aget_object_or_404

    config = await aget_object_or_404(AgentConfiguration, pk=pk)
    codex_url = await _resolve_codex_url_async(config)
    if not codex_url:
        return JsonResponse({"error": "Codex service URL is not configured."}, status=400)
    try:
        # Codex blocks up to ~60s waiting for the device prompt before replying.
        async with httpx.AsyncClient(timeout=75) as client:
            resp = await client.post(
                f"{codex_url}/auth/device/start", headers=_gateway_auth_headers()
            )
    except httpx.HTTPError:
        return JsonResponse({"error": "Unable to reach the Codex service."}, status=502)
    if resp.status_code != 200:
        detail = None
        try:
            detail = resp.json().get("error")
        except Exception:
            pass
        return JsonResponse({"error": detail or "Could not start sign-in."}, status=502)
    return JsonResponse(resp.json())


@staff_required
async def agent_device_login_status(request: HttpRequest, pk: str, login_id: str) -> HttpResponse:
    """Poll a device login; persist the credential on completion."""
    from django.shortcuts import aget_object_or_404

    config = await aget_object_or_404(AgentConfiguration, pk=pk)
    codex_url = await _resolve_codex_url_async(config)
    if not codex_url:
        return JsonResponse({"error": "Codex service URL is not configured."}, status=400)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{codex_url}/auth/device/status/{login_id}",
                headers=_gateway_auth_headers(),
            )
    except httpx.HTTPError:
        return JsonResponse({"error": "Unable to reach the Codex service."}, status=502)
    if resp.status_code == 404:
        return JsonResponse({"status": "not_found"}, status=404)
    data = resp.json()
    status = data.get("status")
    if status == "complete":
        token = data.get("auth_token", "")
        if token:
            from asgiref.sync import sync_to_async

            config.auth_token = token
            await sync_to_async(get(AgentService).save_config)(config)
        return JsonResponse({"status": "complete"})
    if status == "error":
        return JsonResponse({"status": "error", "error": data.get("error", "")})
    return JsonResponse(
        {
            "status": status or "pending",
            "verification_url": data.get("verification_url"),
            "user_code": data.get("user_code"),
        }
    )


@staff_required
@require_POST
def agent_activate_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Activate an agent via HTMX — returns updated status badge."""
    obj = get_object_or_404(AgentConfiguration, pk=pk)
    obj.is_active = True
    get(AgentService).save_config(obj)
    response = HttpResponse()
    response["HX-Redirect"] = request.META.get("HTTP_REFERER", "/control/agents/")
    return response
