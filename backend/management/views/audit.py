"""Audit logs, doc/chart generation logs, and chat session inspection."""

from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from engine.models import (
    ChartGenerationLog,
    ChatMessage,
    ChatSession,
    DocGenerationLog,
    QueryAuditLog,
)

from management.views._helpers import staff_required


@staff_required
def audit_list_view(request: HttpRequest) -> HttpResponse:
    qs = QueryAuditLog.objects.select_related("user", "database").order_by("-created_at")

    success_filter = request.GET.get("success")
    if success_filter == "1":
        qs = qs.filter(success=True)
    elif success_filter == "0":
        qs = qs.filter(success=False)

    qs = qs[:200]

    return render(
        request,
        "management/audit/list.html",
        {
            "logs": qs,
            "section": "audit",
            "success_filter": success_filter,
        },
    )


@staff_required
def docgen_log_list_view(request: HttpRequest) -> HttpResponse:
    qs = DocGenerationLog.objects.select_related("user", "agent").order_by("-started_at")

    status_filter = request.GET.get("status")
    if status_filter in ("success", "partial", "failed"):
        qs = qs.filter(status=status_filter)

    qs = qs[:200]

    return render(
        request,
        "management/docgen_logs/list.html",
        {
            "logs": qs,
            "section": "docgen_logs",
            "status_filter": status_filter,
        },
    )


@staff_required
def docgen_log_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    log_entry = get_object_or_404(
        DocGenerationLog.objects.select_related("user", "agent"),
        pk=pk,
    )
    return render(
        request,
        "management/docgen_logs/detail.html",
        {
            "log": log_entry,
            "section": "docgen_logs",
        },
    )


@staff_required
def chartgen_log_list_view(request: HttpRequest) -> HttpResponse:
    logs = ChartGenerationLog.objects.select_related("user", "agent").all()[:200]
    return render(
        request,
        "management/chartgen_logs/list.html",
        {
            "logs": logs,
            "section": "chartgen_logs",
        },
    )


@staff_required
def chartgen_log_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    log_entry = get_object_or_404(ChartGenerationLog.objects.select_related("user", "agent"), pk=pk)
    return render(
        request,
        "management/chartgen_logs/detail.html",
        {
            "log": log_entry,
            "section": "chartgen_logs",
        },
    )


@staff_required
def session_list_view(request: HttpRequest) -> HttpResponse:
    show_empty = request.GET.get("empty") == "1"
    sessions = (
        ChatSession.objects.select_related("user")
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")
    )
    if not show_empty:
        sessions = sessions.filter(message_count__gt=0)
    sessions = sessions[:200]
    return render(
        request,
        "management/sessions/list.html",
        {
            "sessions": sessions,
            "show_empty": show_empty,
            "section": "sessions",
        },
    )


@staff_required
def session_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    session = get_object_or_404(ChatSession.objects.select_related("user"), pk=pk)
    # NB: don't name this "messages" — that key collides with the
    # django.contrib.messages context variable that base.html renders as flash
    # banners, which would dump the whole transcript above the page title.
    return render(
        request,
        "management/sessions/detail.html",
        {
            "session": session,
            "session_messages": ChatMessage.objects.filter(session=session),
            "section": "sessions",
        },
    )
