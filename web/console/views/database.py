"""Database connection CRUD and connectivity tests."""

from __future__ import annotations

from core.models import DatabaseConnection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from console.views._helpers import staff_required

from ..forms import DatabaseConnectionForm


@staff_required
def database_list_view(request: HttpRequest) -> HttpResponse:
    connections = DatabaseConnection.objects.all()
    return render(
        request,
        "console/databases/list.html",
        {
            "connections": connections,
            "section": "databases",
        },
    )


@staff_required
def database_engine_picker_view(request: HttpRequest) -> HttpResponse:
    """Step 1 of Add Connection: choose a database engine."""
    return render(
        request,
        "console/databases/engine_picker.html",
        {
            "engine_choices": DatabaseConnection.ENGINE_CHOICES,
            "section": "databases",
        },
    )


@staff_required
def database_form_view(
    request: HttpRequest, pk: int | None = None, engine: str | None = None
) -> HttpResponse:
    instance = get_object_or_404(DatabaseConnection, pk=pk) if pk else None

    valid_engines = {key for key, _ in DatabaseConnection.ENGINE_CHOICES}
    if engine and engine not in valid_engines:
        return redirect("console:database_add")

    if request.method == "POST":
        form = DatabaseConnectionForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("console:database_list")
    else:
        initial: dict[str, object] = {"engine": engine} if engine else {}
        if engine and not instance and engine in DatabaseConnection.DEFAULT_PORTS:
            initial["port"] = DatabaseConnection.DEFAULT_PORTS[engine]
        form = DatabaseConnectionForm(instance=instance, initial=initial)

    engine_display = None
    if engine:
        engine_display = dict(DatabaseConnection.ENGINE_CHOICES).get(engine)

    return render(
        request,
        "console/databases/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "databases",
            "engine_key": engine,
            "engine_display": engine_display,
            "is_new_with_engine": bool(engine and not instance),
        },
    )


@staff_required
@require_POST
def database_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(DatabaseConnection, pk=pk)
    obj.delete()
    return redirect("console:database_list")


@staff_required
def database_test_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Test a database connection and return HTMX fragment."""
    from core.engines.db_runner import ping

    obj = get_object_or_404(DatabaseConnection, pk=pk)
    try:
        ping(obj)
        return HttpResponse('<span class="badge badge-success">Connected ✓</span>')
    except Exception as e:
        return HttpResponse(f'<span class="badge badge-error">Failed: {e}</span>')
