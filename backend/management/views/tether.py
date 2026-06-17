"""Tether CRUD + AI generation background task."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from engine.models import Tether, TetherVersion

from management.views._helpers import staff_required

from ..forms import TetherForm


def _start_tether_generation(tether: Tether, user: User) -> TetherVersion:
    """Create a new TetherVersion and run the generator in a background thread.

    Mirrors the docs/dashboard generation pattern — generation runs inside the
    web container so CODEX_SERVICE_URL is available, and the version row is
    updated continuously so the detail page can poll for live status.
    """
    import threading

    last = TetherVersion.objects.filter(tether=tether).order_by("-version_number").first()
    next_number = (last.version_number + 1) if last else 1
    version = TetherVersion.objects.create(
        tether=tether,
        version_number=next_number,
        status="running",
        triggered_by=user,
    )

    def _run(version_pk: str) -> None:
        import django

        django.setup()
        from engine.engines.tether_engine import generate_tether
        from engine.models import TetherVersion

        v = TetherVersion.objects.select_related(
            "tether",
            "tether__codebase",
            "tether__database_doc_source",
        ).get(pk=version_pk)
        generate_tether(v)

    threading.Thread(target=_run, args=(version.pk,), daemon=True).start()
    return version


@staff_required
def tether_list_view(request: HttpRequest) -> HttpResponse:
    tethers = Tether.objects.select_related(
        "codebase",
        "database_doc_source",
        "current_version",
    ).all()
    rows = []
    for tether in tethers:
        latest = TetherVersion.objects.filter(tether=tether).order_by("-version_number").first()
        rows.append({"tether": tether, "latest": latest})
    return render(
        request,
        "management/tethers/list.html",
        {
            "rows": rows,
            "section": "tethers",
        },
    )


@staff_required
def tether_form_view(request: HttpRequest, pk: str | None = None) -> HttpResponse:
    instance = get_object_or_404(Tether, pk=pk) if pk else None

    if not isinstance(request.user, User):
        return JsonResponse({"error": "Forbidden"}, status=403)
    if request.method == "POST":
        form = TetherForm(request.POST, instance=instance)
        if form.is_valid():
            tether = form.save(commit=False)
            if not instance:
                tether.created_by = request.user
            tether.save()
            form.save_m2m()
            if not instance:
                _start_tether_generation(tether, request.user)
            return redirect("management:tether_detail", pk=tether.pk)
    else:
        form = TetherForm(instance=instance)

    return render(
        request,
        "management/tethers/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "tethers",
        },
    )


@staff_required
def tether_detail_view(request: HttpRequest, pk: str) -> HttpResponse:
    tether = get_object_or_404(
        Tether.objects.select_related("codebase", "database_doc_source", "current_version"),
        pk=pk,
    )
    versions = list(TetherVersion.objects.filter(tether=tether).select_related("triggered_by"))
    latest = versions[0] if versions else None
    return render(
        request,
        "management/tethers/detail.html",
        {
            "tether": tether,
            "versions": versions,
            "latest": latest,
            "section": "tethers",
        },
    )


@staff_required
@require_POST
def tether_regenerate_view(request: HttpRequest, pk: str) -> HttpResponse:
    if not isinstance(request.user, User):
        return JsonResponse({"error": "Forbidden"}, status=403)
    tether = get_object_or_404(Tether, pk=pk)
    _start_tether_generation(tether, request.user)
    return redirect("management:tether_detail", pk=tether.pk)


@staff_required
@require_POST
def tether_delete_view(request: HttpRequest, pk: str) -> HttpResponse:
    tether = get_object_or_404(Tether, pk=pk)
    tether.delete()
    return redirect("management:tether_list")


@staff_required
def tether_version_detail_view(request: HttpRequest, pk: str, version_pk: str) -> HttpResponse:
    tether = get_object_or_404(Tether, pk=pk)
    version = get_object_or_404(
        TetherVersion.objects.select_related("triggered_by"),
        pk=version_pk,
        tether=tether,
    )
    return render(
        request,
        "management/tethers/version_detail.html",
        {
            "tether": tether,
            "version": version,
            "section": "tethers",
        },
    )


@staff_required
def tether_status_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Polling endpoint: latest version status + live agent thoughts."""
    tether = get_object_or_404(Tether.objects.select_related("current_version"), pk=pk)
    latest = TetherVersion.objects.filter(tether=tether).order_by("-version_number").first()
    if latest is None:
        return JsonResponse({"status": "none"})
    return JsonResponse(
        {
            "status": latest.status,
            "version_number": latest.version_number,
            "version_pk": latest.pk,
            "agent_output": latest.agent_log_excerpt,
            "error": latest.error_message,
            "execution_time_ms": latest.execution_time_ms,
            "is_current": tether.current_version_id == latest.pk,
        }
    )
