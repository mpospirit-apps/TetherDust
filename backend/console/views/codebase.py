"""Codebase source CRUD and on-demand GitHub sync."""

from __future__ import annotations

from core.models import Codebase
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from console.views._helpers import staff_required

from ..forms import CodebaseForm


@staff_required
def codebase_list_view(request: HttpRequest) -> HttpResponse:
    codebases = Codebase.objects.all()
    return render(
        request,
        "console/codebases/list.html",
        {
            "codebases": codebases,
            "section": "codebases",
        },
    )


@staff_required
def codebase_provider_picker_view(request: HttpRequest) -> HttpResponse:
    """Step 1 of Add Codebase: choose a provider (GitHub only for now)."""
    return render(
        request,
        "console/codebases/provider_picker.html",
        {
            "provider_choices": Codebase.PROVIDER_CHOICES,
            "section": "codebases",
        },
    )


@staff_required
def codebase_form_view(
    request: HttpRequest, pk: int | None = None, provider: str | None = None
) -> HttpResponse:
    instance = get_object_or_404(Codebase, pk=pk) if pk else None

    valid_providers = {key for key, _ in Codebase.PROVIDER_CHOICES}
    if provider and provider not in valid_providers:
        return redirect("console:codebase_add")

    if request.method == "POST":
        form = CodebaseForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            assert isinstance(saved, Codebase)
            # Kick off an initial sync so the file tree is cached right away.
            _enqueue_sync(saved.pk)
            return redirect("console:codebase_list")
    else:
        initial: dict[str, object] = {"provider": provider} if provider else {}
        form = CodebaseForm(instance=instance, initial=initial)

    provider_display = None
    if provider:
        provider_display = dict(Codebase.PROVIDER_CHOICES).get(provider)

    return render(
        request,
        "console/codebases/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "codebases",
            "provider_key": provider,
            "provider_display": provider_display,
            "is_new_with_provider": bool(provider and not instance),
        },
    )


@staff_required
@require_POST
def codebase_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Codebase, pk=pk)
    obj.delete()
    return redirect("console:codebase_list")


@staff_required
@require_POST
def codebase_sync_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a codebase as syncing, enqueue the sync, and return to the list.

    The list row then polls ``codebase_status`` until the sync settles.
    """
    obj = get_object_or_404(Codebase, pk=pk)
    obj.sync_status = Codebase.SYNC_SYNCING
    obj.sync_error = ""
    obj.save(update_fields=["sync_status", "sync_error", "updated_at"])
    _enqueue_sync(obj.pk)
    return redirect("console:codebase_list")


@staff_required
def codebase_status_view(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX poll target: returns the current sync-status cell."""
    obj = get_object_or_404(Codebase, pk=pk)
    html = render_to_string("console/codebases/_status.html", {"cb": obj}, request=request)
    return HttpResponse(html)


def _enqueue_sync(codebase_id: int) -> None:
    """Dispatch the sync task, falling back to inline run if Celery is down."""
    from core.tasks import sync_codebase

    try:
        sync_codebase.delay(codebase_id)
    except Exception:
        # Broker unavailable (e.g. local dev without Redis) — run synchronously.
        sync_codebase(codebase_id)
