"""Role and UserProfile models for role-based access control."""

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import generate_rol_id, generate_usp_id
from .connections import (
    Codebase,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    ToolConfiguration,
)


class Role(models.Model):
    """Admin-configurable role with granular permissions."""

    class Meta:
        verbose_name = "role"
        verbose_name_plural = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    __prefix__: ClassVar[str] = "rol"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_rol_id, editable=False)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)

    # Domain
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    max_row_limit = models.IntegerField(
        verbose_name="max row limit", default=100, help_text="Maximum rows per query"
    )
    can_manage_users = models.BooleanField(verbose_name="can manage users", default=False)
    can_chat = models.BooleanField(
        verbose_name="can chat",
        default=True,
        help_text="Allow users with this role to use the chat interface.",
    )
    can_view_tethers = models.BooleanField(
        verbose_name="can view tethers",
        default=True,
        help_text="Allow users with this role to view Tethers.",
    )
    is_admin_role = models.BooleanField(
        verbose_name="is admin role",
        default=False,
        help_text="Admin roles bypass all access restrictions. Access control settings are ignored.",  # noqa: E501
    )

    # Relations
    allowed_tools = models.ManyToManyField(ToolConfiguration, blank=True, related_name="roles")
    allowed_databases = models.ManyToManyField(DatabaseConnection, blank=True, related_name="roles")
    allowed_doc_sources = models.ManyToManyField(
        DocumentationSource, blank=True, related_name="roles_docs"
    )
    allowed_codebases = models.ManyToManyField(Codebase, blank=True, related_name="roles")
    allowed_prompts = models.ManyToManyField(PromptConfiguration, blank=True, related_name="roles")
    # Custom MCP servers are explicit allow-list: empty = role can only use the
    # built-in server. The built-in server is always available regardless of this M2M.
    allowed_mcp_servers = models.ManyToManyField(
        MCPServerConfiguration,
        blank=True,
        related_name="roles",
    )

    def __str__(self) -> str:
        return self.name


class UserProfile(models.Model):
    """Extended user profile linking a user to a role.

    Permission resolution lives in
    :class:`engine.services.permissions.PermissionService`.
    """

    class Meta:
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"

    __prefix__: ClassVar[str] = "usp"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_usp_id, editable=False)

    # Relations
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self) -> str:
        role_name = self.role.name if self.role else "No Role"
        return f"{self.user.username} ({role_name})"
