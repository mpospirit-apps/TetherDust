"""User-facing Tether views: list, viewer page, and graph JSON endpoint."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


@login_required
def tethers_list_view(request: HttpRequest) -> HttpResponse:
    from engine.models import UserProfile

    try:
        profile = getattr(request.user, "profile")
    except UserProfile.DoesNotExist:
        return render(
            request,
            "workspace/tethers/list.html",
            {
                "tethers": [],
                "has_access": False,
                "current_tether_id": None,
            },
        )
    tethers = profile.get_allowed_tethers().select_related("current_version").order_by("name")
    return render(
        request,
        "workspace/tethers/list.html",
        {
            "tethers": tethers,
            "has_access": True,
            "current_tether_id": None,
        },
    )


@login_required
def tether_view(request: HttpRequest, pk: int) -> HttpResponse:
    from engine.models import UserProfile

    try:
        profile = getattr(request.user, "profile")
    except UserProfile.DoesNotExist:
        raise Http404
    allowed = profile.get_allowed_tethers().select_related(
        "current_version", "codebase", "database_doc_source"
    )
    tether = allowed.filter(pk=pk).first()
    if tether is None:
        raise Http404
    all_tethers = allowed.order_by("name")
    return render(
        request,
        "workspace/tethers/viewer.html",
        {
            "tether": tether,
            "tethers": all_tethers,
            "current_tether_id": tether.pk,
            "has_access": True,
        },
    )


@login_required
def tether_graph_json_view(request: HttpRequest, pk: int) -> HttpResponse:
    from engine.models import UserProfile

    try:
        profile = getattr(request.user, "profile")
    except UserProfile.DoesNotExist:
        raise Http404
    tether = profile.get_allowed_tethers().select_related("current_version").filter(pk=pk).first()
    if tether is None:
        raise Http404
    if tether.current_version is None:
        return JsonResponse({"nodes": [], "edges": [], "schema_version": 1, "status": "pending"})
    return JsonResponse(tether.current_version.graph_json or {"nodes": [], "edges": []})
