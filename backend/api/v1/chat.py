"""Public chat-support endpoints (the live chat itself runs over the WebSocket).

- session list (grouped by recency) + delete, for the chat sidebar
- doc-source resources (for `@` mentions) and prompts (for `/` slash commands),
  both role-filtered — ports of the legacy `sessions_list_view`,
  `session_delete_view`, `doc_sources_api_view`, `prompts_api_view`.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import httpx
from django.db.models import Count
from django.utils import timezone
from engine.models import ChatSession, PromptConfiguration, UserProfile
from engine.services import PermissionService, get
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanChat

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser, User

logger = logging.getLogger(__name__)


class ChatSessionsView(APIView):
    permission_classes = [CanChat]

    def get(self, request: Request) -> Response:
        sessions = (
            ChatSession.objects.filter(user=cast("User", request.user))
            .annotate(message_count=Count("messages"))
            .filter(message_count__gt=0)
            .order_by("-updated_at")
            .values("id", "title", "updated_at", "message_count")
        )
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        result: list[dict[str, Any]] = []
        for s in sessions:
            updated = s["updated_at"]
            if updated >= today_start:
                group = "Today"
            elif updated >= yesterday_start:
                group = "Yesterday"
            else:
                day_start = updated.replace(hour=0, minute=0, second=0, microsecond=0)
                days_ago = (today_start - day_start).days
                group = updated.strftime("%A") if days_ago <= 7 else updated.strftime("%B %Y")
            result.append(
                {
                    "id": s["id"],
                    "title": s["title"] or f"Session {s['id']}",
                    "group": group,
                    "updated_at": updated.isoformat(),
                    "message_count": s["message_count"],
                }
            )
        return Response({"sessions": result})


class ChatSessionDetailView(APIView):
    permission_classes = [CanChat]

    def delete(self, request: Request, session_id: str) -> Response:
        try:
            session = ChatSession.objects.get(id=session_id, user=cast("User", request.user))
        except ChatSession.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocSourcesView(APIView):
    """MCP documentation resources accessible to the user (for `@` mentions)."""

    permission_classes = [CanChat]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        allowed_names = None
        if not user.is_staff:
            try:
                profile = getattr(user, "profile")
            except UserProfile.DoesNotExist:
                return Response({"resources": []})
            allowed_names = get(PermissionService).get_allowed_doc_sources(profile)
            if allowed_names is not None and not allowed_names:
                return Response({"resources": []})

        mcp_base_url = os.environ.get("MCP_BASE_URL", "http://localhost:8001")
        params: dict[str, str] = {}
        if allowed_names is not None:
            params["allowed_doc_sources"] = ",".join(sorted(allowed_names))
        query = request.query_params.get("q", "").strip()
        if query:
            params["q"] = query
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.get(f"{mcp_base_url}/list-resources", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.warning("Failed to fetch resources from MCP server at %s", mcp_base_url)
            return Response({"resources": []})
        return Response({"resources": data.get("resources", [])})


class PromptsView(APIView):
    """MCP prompts accessible to the user (for `/` slash commands)."""

    permission_classes = [CanChat]

    def get(self, request: Request) -> Response:
        user = cast("AbstractUser", request.user)
        if user.is_staff:
            prompts = PromptConfiguration.objects.filter(
                is_enabled=True, mcp_server__is_active=True
            )
        else:
            try:
                profile = getattr(user, "profile")
            except UserProfile.DoesNotExist:
                return Response({"prompts": []})
            allowed_names = get(PermissionService).get_allowed_prompts(profile)
            if allowed_names is not None and not allowed_names:
                return Response({"prompts": []})
            if allowed_names is None:
                prompts = PromptConfiguration.objects.filter(
                    is_enabled=True, mcp_server__is_active=True
                )
            else:
                prompts = PromptConfiguration.objects.filter(
                    is_enabled=True, mcp_server__is_active=True, prompt_name__in=allowed_names
                )
        result = [
            {"name": p.prompt_name, "display_name": p.display_name, "content": p.content}
            for p in prompts
        ]
        return Response({"prompts": result})
