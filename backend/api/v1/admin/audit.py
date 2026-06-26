"""Read-only monitoring viewers: query audit log + chat sessions.

Doc/chart-generation and report-run logs are feature-coupled and ship with their
verticals (V1/V2/V3); this module covers the always-relevant audit + sessions.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count
from engine.models import ChatMessage, ChatSession, QueryAuditLog
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsStaffUser


class AuditLogView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        qs = QueryAuditLog.objects.select_related("user", "database").order_by("-created_at")
        success = request.query_params.get("success")
        if success == "1":
            qs = qs.filter(success=True)
        elif success == "0":
            qs = qs.filter(success=False)
        results: list[dict[str, Any]] = [
            {
                "id": log.id,
                "created_at": log.created_at.isoformat(),
                "user": log.user.username if log.user else None,
                "database": log.database.name if log.database else None,
                "success": log.success,
                "row_count": log.row_count,
                "execution_time_ms": log.execution_time_ms,
                "query": log.query,
                "error_message": log.error_message,
            }
            for log in qs[:200]
        ]
        return Response({"results": results})


class SessionsView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        qs = ChatSession.objects.annotate(message_count=Count("messages")).order_by("-updated_at")
        if request.query_params.get("empty") != "1":
            qs = qs.filter(message_count__gt=0)
        rows = qs.values("id", "title", "updated_at", "user__username", "message_count")[:200]
        results: list[dict[str, Any]] = [
            {
                "id": r["id"],
                "title": r["title"],
                "user": r["user__username"],
                "message_count": r["message_count"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
        return Response({"results": results})


class SessionDetailView(APIView):
    """A single chat session's full transcript (admin monitoring).

    Ports the legacy ``session_detail_view``: session metadata + every
    ``ChatMessage`` in order, with the per-message tools/sources/prompts.
    """

    permission_classes = [IsStaffUser]

    def get(self, request: Request, session_id: str) -> Response:
        try:
            session = ChatSession.objects.select_related("user").get(pk=session_id)
        except ChatSession.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        messages: list[dict[str, Any]] = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tools_used": m.tools_used,
                "sources_used": m.sources_used,
                "prompts_used": m.prompts_used,
                "created_at": m.created_at.isoformat(),
            }
            for m in ChatMessage.objects.filter(session=session)
        ]
        return Response(
            {
                "id": session.id,
                "title": session.title,
                "user": session.user.username if session.user else None,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": len(messages),
                "messages": messages,
            }
        )
