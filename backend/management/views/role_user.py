"""Roles, permissions, and user management."""

from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from engine.models import (
    MCPServerConfiguration,
    PromptConfiguration,
    Role,
    ToolConfiguration,
    UserProfile,
)

from management.views._helpers import staff_required

from ..forms import RoleForm, UserCreateForm, UserProfileForm


def _posted_pk_set(data: QueryDict, key: str) -> set[int]:
    values = set()
    for value in data.getlist(key):
        try:
            values.add(int(value))
        except (TypeError, ValueError):
            pass
    return values


@staff_required
def role_list_view(request: HttpRequest) -> HttpResponse:
    roles = Role.objects.annotate(
        tool_count=Count("allowed_tools"),
        db_count=Count("allowed_databases"),
        user_count=Count("userprofile"),
    )
    return render(
        request,
        "management/roles/list.html",
        {
            "roles": roles,
            "section": "roles",
        },
    )


@staff_required
def role_form_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    instance = get_object_or_404(Role, pk=pk) if pk else None
    if request.method == "POST":
        form = RoleForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("management:role_list")
    else:
        form = RoleForm(instance=instance)

    mcp_servers = MCPServerConfiguration.objects.prefetch_related("tools", "prompts").filter(
        is_active=True
    )
    if request.method == "POST":
        selected_tool_ids = _posted_pk_set(request.POST, "allowed_tools")
        selected_prompt_ids = _posted_pk_set(request.POST, "allowed_prompts")
    elif instance:
        selected_tool_ids = set(instance.allowed_tools.values_list("pk", flat=True))
        selected_prompt_ids = set(instance.allowed_prompts.values_list("pk", flat=True))
    else:
        selected_tool_ids = set(
            ToolConfiguration.objects.filter(mcp_server__in=mcp_servers).values_list(
                "pk", flat=True
            )
        )
        selected_prompt_ids = set(
            PromptConfiguration.objects.filter(mcp_server__in=mcp_servers).values_list(
                "pk", flat=True
            )
        )

    return render(
        request,
        "management/roles/form.html",
        {
            "form": form,
            "instance": instance,
            "mcp_servers": mcp_servers,
            "selected_tool_ids": selected_tool_ids,
            "selected_prompt_ids": selected_prompt_ids,
            "section": "roles",
        },
    )


@staff_required
@require_POST
def role_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    from django.contrib import messages
    from django.db.models.deletion import ProtectedError

    obj = get_object_or_404(Role, pk=pk)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete role '{obj.name}' because it is assigned to one or more users. "
            "Reassign those users to a different role first.",
        )
    return redirect("management:role_list")


def _require_user_management(request: HttpRequest) -> HttpResponse | None:
    """Returns HttpResponseForbidden if user cannot manage users. Superusers are always allowed."""
    if getattr(request.user, "is_superuser", False):
        return None
    profile = getattr(request.user, "profile", None)
    if not profile or not profile.role or not profile.role.can_manage_users:
        return HttpResponseForbidden("You do not have permission to manage users.")
    return None


@staff_required
def user_list_view(request: HttpRequest) -> HttpResponse:
    if err := _require_user_management(request):
        return err
    users = User.objects.select_related("profile", "profile__role").order_by("username")
    return render(
        request,
        "management/users/list.html",
        {
            "users": users,
            "section": "users",
        },
    )


@staff_required
def user_create_view(request: HttpRequest) -> HttpResponse:
    """Create a new user with optional role assignment."""
    if err := _require_user_management(request):
        return err
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("management:user_list")
    else:
        form = UserCreateForm()

    return render(
        request,
        "management/users/create.html",
        {
            "form": form,
            "section": "users",
        },
    )


@staff_required
def user_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    if err := _require_user_management(request):
        return err
    user_obj = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user_obj)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("management:user_list")
    else:
        form = UserProfileForm(instance=profile)

    return render(
        request,
        "management/users/form.html",
        {
            "form": form,
            "user_obj": user_obj,
            "section": "users",
        },
    )


@staff_required
@require_POST
def user_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a user account."""
    if err := _require_user_management(request):
        return err
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj == request.user:
        return redirect("management:user_list")
    user_obj.delete()
    return redirect("management:user_list")
