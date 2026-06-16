"""Forms for roles, user profiles, and user creation."""

from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib.auth.models import User
from django.db.models import Model as DjangoModel
from django.forms import ModelMultipleChoiceField
from engine.forms.base import _BaseForm
from engine.models import (
    Codebase,
    Dashboard,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    ReportDefinition,
    Role,
    ToolConfiguration,
    UserProfile,
)


class RoleForm(_BaseForm):
    DEFAULT_CHECKED_ACCESS_FIELDS = (
        "allowed_tools",
        "allowed_databases",
        "allowed_doc_sources",
        "allowed_codebases",
        "allowed_prompts",
        "allowed_reports",
        "allowed_dashboards",
        "allowed_mcp_servers",
    )

    allowed_tools = forms.ModelMultipleChoiceField(
        queryset=ToolConfiguration.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_databases = forms.ModelMultipleChoiceField(
        queryset=DatabaseConnection.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_doc_sources = forms.ModelMultipleChoiceField(
        queryset=DocumentationSource.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Documentation Sources",
        help_text="Documentation sources visible to users with this role",
    )
    allowed_codebases = forms.ModelMultipleChoiceField(
        queryset=Codebase.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Codebases",
        help_text="Codebases visible to users with this role",
    )
    allowed_prompts = forms.ModelMultipleChoiceField(
        queryset=PromptConfiguration.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Prompts",
        help_text="Prompts available to users with this role",
    )
    allowed_reports = forms.ModelMultipleChoiceField(
        queryset=ReportDefinition.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Reports",
        help_text="Reports visible to users with this role",
    )
    allowed_dashboards = forms.ModelMultipleChoiceField(
        queryset=Dashboard.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Dashboards",
        help_text="Dashboards visible to users with this role",
    )
    allowed_mcp_servers = forms.ModelMultipleChoiceField(
        queryset=MCPServerConfiguration.objects.filter(is_active=True, is_builtin=False),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="MCP Servers",
        help_text="Custom MCP servers this role may use. The built-in server is always available.",
    )

    class Meta:
        model = Role
        fields = [
            "name",
            "description",
            "is_active",
            "can_chat",
            "can_view_tethers",
            "can_manage_users",
            "is_admin_role",
            "max_row_limit",
            "allowed_tools",
            "allowed_databases",
            "allowed_doc_sources",
            "allowed_codebases",
            "allowed_prompts",
            "allowed_reports",
            "allowed_dashboards",
            "allowed_mcp_servers",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        initial = kwargs.get("initial")
        explicit_initial: dict[str, object] = initial if isinstance(initial, dict) else {}
        super().__init__(*args, **kwargs)
        self.fields["can_manage_users"].help_text = (
            "Only applies to staff users. Without Admin role, this does not "
            "grant management access; it only lets a staff user manage users."
        )
        self.fields["is_admin_role"].help_text = (
            "Makes assigned non-superusers staff, grants management access, and "
            "bypasses role allow-lists. User management still also requires "
            "Can manage users or superuser status."
        )
        if not self.is_bound and not self.instance.pk:
            self._default_access_controls_checked(explicit_initial)

    def _default_access_controls_checked(self, explicit_initial: dict[str, object]) -> None:
        for field_name in self.DEFAULT_CHECKED_ACCESS_FIELDS:
            if field_name in explicit_initial:
                continue
            qs = cast(ModelMultipleChoiceField[DjangoModel], self.fields[field_name]).queryset
            if qs is not None:
                self.initial[field_name] = list(qs.values_list("pk", flat=True))

    def save(self, commit: bool = True) -> object:
        role = super().save(commit=commit)
        if commit:
            # Propagate is_admin_role to every user holding this role so that
            # management access stays aligned with the role's admin flag.
            # Superusers are left untouched — they retain staff access regardless.
            User.objects.filter(profile__role=role, is_superuser=False).update(
                is_staff=role.is_admin_role
            )
        return role


class UserProfileForm(_BaseForm):
    class Meta:
        model = UserProfile
        fields = ["role"]

    def save(self, commit: bool = True) -> object:
        profile = super().save(commit=commit)
        if commit:
            user = profile.user
            # Keep User.is_staff aligned with role.is_admin_role. Never demote
            # superusers — they retain staff access independent of role.
            if not user.is_superuser:
                want_staff = bool(profile.role and profile.role.is_admin_role)
                if user.is_staff != want_staff:
                    user.is_staff = want_staff
                    user.save(update_fields=["is_staff"])
        return profile


if TYPE_CHECKING:
    _UserModelForm = forms.ModelForm[User]
else:
    _UserModelForm = forms.ModelForm


class UserCreateForm(_UserModelForm):
    """Form to create a new Django User with an optional role assignment."""

    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    is_active = forms.BooleanField(required=False, initial=True)
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=False,
        help_text=(
            "Assign a role to this user. Admin roles grant management access and "
            "sync non-superusers to staff."
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "is_active"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        skip = (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)
        for field in self.fields.values():
            if not isinstance(field.widget, skip):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        pw = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned

    def save(self, commit: bool = True) -> User:
        role = self.cleaned_data.get("role")
        is_staff = bool(role and role.is_admin_role)
        user = User(
            username=self.cleaned_data["username"],
            email=self.cleaned_data.get("email", ""),
            is_staff=is_staff,
            is_active=self.cleaned_data.get("is_active", True),
        )
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            # Signal may have already created a profile; update it with the chosen role.
            UserProfile.objects.update_or_create(user=user, defaults={"role": role})
        return user
