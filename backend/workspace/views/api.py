"""Auth, health, agent status, and small cross-cutting JSON endpoints."""

from __future__ import annotations

import datetime
import logging
import os
from typing import TYPE_CHECKING, cast

import httpx
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def _default_redirect(user: AbstractUser) -> str:
    """Return the default post-login URL based on user type and role access."""
    if user.is_staff:
        return "management:dashboard"
    profile = getattr(user, "profile", None)
    if profile and profile.can_chat:
        return "workspace:chat"
    if profile and profile.can_view_dashboards:
        return "workspace:dashboards"
    if profile and profile.can_view_reports:
        return "workspace:reports"
    if profile and profile.can_view_docs:
        return "workspace:docs"
    return "workspace:chat"


def login_view(request: HttpRequest) -> HttpResponse:
    """Unified login page for all users (staff and regular)."""
    if request.user.is_authenticated:
        return redirect(_default_redirect(cast("AbstractUser", request.user)))

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Only honor `next` if it points back at this site — otherwise an
            # attacker could craft …/login/?next=https://evil.com to bounce the
            # user off-site after a real login (open redirect / phishing aid).
            next_url = request.POST.get("next") or request.GET.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect(_default_redirect(cast("AbstractUser", user)))
        else:
            error = "Invalid credentials."

    return render(request, "workspace/login.html", {"error": error})


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out and redirect to login."""
    logout(request)
    return redirect("workspace:login")


def healthz_view(request: HttpRequest) -> JsonResponse:
    """Liveness probe — returns 200 if the process is running."""
    return JsonResponse({"status": "ok"})


def readyz_view(request: HttpRequest) -> JsonResponse:
    """Readiness probe — checks Django DB and configured database connections."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        connection.ensure_connection()
        checks["django_db"] = "ok"
    except Exception as e:
        checks["django_db"] = str(e)
        healthy = False

    try:
        from engine.engines.db_runner import ping
        from engine.models import DatabaseConnection

        active_dbs = DatabaseConnection.objects.filter(is_active=True)
        for db in active_dbs:
            try:
                ping(db)
                checks[f"db:{db.name}"] = "ok"
            except Exception as e:
                checks[f"db:{db.name}"] = str(e)
                healthy = False
    except Exception as e:
        checks["configured_dbs"] = f"check failed: {e}"

    status_code = 200 if healthy else 503
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks}, status=status_code
    )


@login_required
def agent_status_view(request: HttpRequest) -> JsonResponse:
    """Return the active agent name and whether its service is reachable and authenticated."""
    from engine.models import AgentConfiguration, SystemConfiguration

    agent_config = AgentConfiguration.get_active()
    if not agent_config:
        return JsonResponse({"name": None, "connected": False})

    name = agent_config.name
    agent_type = agent_config.agent_type

    # API-key agents are "connected" when a key is configured — no container check needed.
    if agent_type in (
        "openai_platform",
        "claude_console",
        "openai_api",
        "openrouter",
        "codex_api",
        "claude_code_api",
    ):
        connected = bool(agent_config.get_api_key())
        return JsonResponse({"name": name, "connected": connected})

    # Ollama runs locally with no key — just verify the service URL is reachable.
    if agent_type == "ollama":
        base_url = (
            isinstance(agent_config.settings, dict) and agent_config.settings.get("base_url") or ""
        ).rstrip("/")
        if not base_url:
            return JsonResponse({"name": name, "connected": True})  # assume local default
        try:
            httpx.get(base_url, timeout=3)
            connected = True
        except Exception:
            connected = False
        return JsonResponse({"name": name, "connected": connected})

    # Claude Code: the OAuth token lives in the encrypted config (not on the
    # container, which has no /auth/token endpoint). "Connected" = gateway
    # reachable AND a token is stored.
    if agent_type == "claude_code":
        db_service_url = SystemConfiguration.get_value("claude_service_url", "") or ""
        service_url = (
            agent_config.service_url or db_service_url or os.environ.get("CLAUDE_SERVICE_URL", "")
        ).rstrip("/")
        if not service_url:
            return JsonResponse({"name": name, "connected": False})
        try:
            healthz = httpx.get(f"{service_url}/healthz", timeout=3)
            reachable = healthz.status_code == 200
        except Exception:
            reachable = False
        connected = reachable and bool(agent_config.get_auth_token())
        return JsonResponse({"name": name, "connected": connected})

    # codex / codex_api via Codex container: check service health first.
    db_service_url = SystemConfiguration.get_value("codex_service_url", "") or ""
    config_service_url = agent_config.service_url or ""
    service_url = (
        config_service_url or db_service_url or os.environ.get("CODEX_SERVICE_URL", "")
    ).rstrip("/")

    if not service_url:
        return JsonResponse({"name": name, "connected": False})

    try:
        healthz = httpx.get(f"{service_url}/healthz", timeout=3)
        if healthz.status_code != 200:
            return JsonResponse({"name": name, "connected": False})
    except Exception:
        return JsonResponse({"name": name, "connected": False})

    # codex (ChatGPT subscription): service is up, but also verify auth.json is
    # present on the container and hasn't expired.
    from engine.agents.gateway import gateway_auth_headers

    try:
        token_resp = httpx.get(
            f"{service_url}/auth/token", timeout=3, headers=gateway_auth_headers()
        )
        token_data = token_resp.json() if token_resp.status_code == 200 else {}
    except Exception:
        token_data = {}

    if not token_data.get("present"):
        return JsonResponse({"name": name, "connected": False})

    expires_at = token_data.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.datetime.fromisoformat(expires_at)
            if expiry <= datetime.datetime.now(tz=datetime.UTC):
                return JsonResponse({"name": name, "connected": False})
        except ValueError:
            pass  # unparseable expiry — treat as not expired

    return JsonResponse({"name": name, "connected": True})


@login_required
def doc_sources_api_view(request: HttpRequest) -> JsonResponse:
    """Return MCP documentation resources accessible to the current user.

    Queries the MCP server's /list-resources endpoint, passing the user's
    allowed doc sources as a filter so the response is role-restricted.
    """
    user = cast("AbstractUser", request.user)

    allowed_names = None
    if not user.is_staff:
        profile = getattr(user, "profile", None)
        if not profile:
            return JsonResponse({"resources": []})
        allowed_names = profile.get_allowed_doc_sources()
        if allowed_names is not None and not allowed_names:
            return JsonResponse({"resources": []})

    mcp_base_url = os.environ.get("MCP_BASE_URL", "http://localhost:8001")
    params = {}
    if allowed_names is not None:
        params["allowed_doc_sources"] = ",".join(sorted(allowed_names))
    query = request.GET.get("q", "").strip()
    if query:
        params["q"] = query

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(f"{mcp_base_url}/list-resources", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Failed to fetch resources from MCP server at %s", mcp_base_url)
        return JsonResponse({"resources": []})

    return JsonResponse({"resources": data.get("resources", [])})


@login_required
def prompts_api_view(request: HttpRequest) -> JsonResponse:
    """Return MCP prompts accessible to the current user, filtered by role."""
    from engine.models import PromptConfiguration

    user = cast("AbstractUser", request.user)

    if user.is_staff:
        prompts = PromptConfiguration.objects.filter(is_enabled=True, mcp_server__is_active=True)
    else:
        profile = getattr(user, "profile", None)
        if not profile:
            return JsonResponse({"prompts": []})
        allowed_names = profile.get_allowed_prompts()
        if allowed_names is not None and not allowed_names:
            return JsonResponse({"prompts": []})
        if allowed_names is None:
            prompts = PromptConfiguration.objects.filter(
                is_enabled=True, mcp_server__is_active=True
            )
        else:
            prompts = PromptConfiguration.objects.filter(
                is_enabled=True,
                mcp_server__is_active=True,
                prompt_name__in=allowed_names,
            )

    result = [
        {
            "name": p.prompt_name,
            "display_name": p.display_name,
            "content": p.content,
        }
        for p in prompts
    ]
    return JsonResponse({"prompts": result})
