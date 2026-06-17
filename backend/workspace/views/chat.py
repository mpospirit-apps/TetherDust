"""Chat interface views: main page and session list/delete endpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from engine.services import PermissionService, get

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def _user_can_chat(user: AbstractUser) -> bool:
    """Return True if the user may access the chat interface."""
    if user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and get(PermissionService).can_chat(profile))


@login_required
def chat_view(request: HttpRequest) -> HttpResponse:
    """Main chat interface for non-technical users."""
    return render(
        request,
        "workspace/chat.html",
        {
            "has_chat_access": _user_can_chat(cast("AbstractUser", request.user)),
        },
    )


@login_required
@require_http_methods(["GET"])
def sessions_list_view(request: HttpRequest) -> HttpResponse:
    """Return the current user's chat sessions as JSON."""
    if not _user_can_chat(cast("AbstractUser", request.user)):
        return JsonResponse({"sessions": []})

    from engine.models import ChatSession

    if not isinstance(request.user, User):
        return JsonResponse({"sessions": []})
    sessions = (
        ChatSession.objects.filter(user=request.user)
        .annotate(message_count=Count("messages"))
        .filter(message_count__gt=0)
        .order_by("-updated_at")
    )

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    result = []
    for s in sessions:
        if s.updated_at >= today_start:
            group = "Today"
        elif s.updated_at >= yesterday_start:
            group = "Yesterday"
        else:
            session_day_start = s.updated_at.replace(hour=0, minute=0, second=0, microsecond=0)
            days_ago = (today_start - session_day_start).days
            if days_ago <= 7:
                group = s.updated_at.strftime("%A")
            else:
                group = s.updated_at.strftime("%B %Y")

        result.append(
            {
                "id": s.pk,
                "title": s.title or f"Session {s.pk}",
                "group": group,
                "updated_at": s.updated_at.isoformat(),
                "message_count": getattr(s, "message_count", 0),
            }
        )

    return JsonResponse({"sessions": result})


@login_required
@require_http_methods(["DELETE"])
def session_delete_view(request: HttpRequest, session_id: str) -> HttpResponse:
    """Delete a chat session owned by the current user."""
    if not _user_can_chat(cast("AbstractUser", request.user)):
        return JsonResponse({"error": "Forbidden"}, status=403)

    from engine.models import ChatSession

    if not isinstance(request.user, User):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
        session.delete()
        return JsonResponse({"ok": True})
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
