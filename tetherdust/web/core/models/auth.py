"""Role and UserProfile models for role-based access control."""

from typing import Any

from django.contrib.auth.models import User
from django.db import models

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

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
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
    max_row_limit = models.IntegerField(default=100, help_text="Maximum rows per query")
    can_manage_users = models.BooleanField(default=False)
    can_chat = models.BooleanField(
        default=True,
        help_text="Allow users with this role to use the chat interface.",
    )
    can_view_tethers = models.BooleanField(
        default=True,
        help_text="Allow users with this role to view Tethers.",
    )
    is_active = models.BooleanField(default=True)
    is_admin_role = models.BooleanField(
        default=False,
        help_text="Admin roles bypass all access restrictions. Access control settings are ignored.",  # noqa: E501
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UserProfile(models.Model):
    """Extended user profile with role and permissions."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self) -> str:
        role_name = self.role.name if self.role else "No Role"
        return f"{self.user.username} ({role_name})"

    def get_max_row_limit(self) -> int | None:
        """Get user's maximum row limit. Returns None for staff (no limit)."""
        if self.user.is_staff:
            return None
        return self.role.max_row_limit if self.role else 100

    def get_allowed_tools(self) -> set[str] | None:
        """Get all tool names the user can access.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the role has no tools assigned (no access).
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        if not self.role:
            return set()
        return set(
            self.role.allowed_tools.filter(is_enabled=True, mcp_server__is_active=True).values_list(
                "tool_name", flat=True
            )
        )

    def get_allowed_databases(self) -> set[str] | None:
        """Get all database names the user can access.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the role has no databases assigned (no access).
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        if not self.role:
            return set()
        return set(
            self.role.allowed_databases.filter(is_active=True).values_list("name", flat=True)
        )

    def get_allowed_doc_sources(self) -> set[str] | None:
        """Get documentation source names the user can access via their role.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the role has no doc sources assigned (no access).
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        if not self.role:
            return set()
        return set(
            self.role.allowed_doc_sources.filter(is_active=True).values_list(
                "folder_name", flat=True
            )
        )

    def get_allowed_codebases(self) -> set[str] | None:
        """Get codebase names the user can access via their role.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the role has no codebases assigned (no access).
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        if not self.role:
            return set()
        return set(
            self.role.allowed_codebases.filter(is_active=True).values_list("name", flat=True)
        )

    def get_allowed_prompts(self) -> set[str] | None:
        """Get all prompt names the user can access.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the role has no prompts assigned (no access).
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        if not self.role:
            return set()
        return set(
            self.role.allowed_prompts.filter(
                is_enabled=True, mcp_server__is_active=True
            ).values_list("prompt_name", flat=True)
        )

    def get_allowed_mcp_servers(self) -> models.QuerySet[MCPServerConfiguration]:
        """Active non-built-in MCP servers the user's role may use.

        Returns an empty queryset if the user has no role. The built-in server
        is always available and is not included here.
        """
        if self.user.is_staff:
            return MCPServerConfiguration.objects.filter(is_active=True, is_builtin=False)
        if not self.role:
            return MCPServerConfiguration.objects.none()
        return self.role.allowed_mcp_servers.filter(is_active=True, is_builtin=False)

    def get_allowed_reports(self) -> models.QuerySet[Any]:
        """Get report definitions the user can access via their role."""
        from .reports import ReportDefinition

        if self.user.is_staff:
            return ReportDefinition.objects.filter(is_active=True)
        if not self.role:
            return ReportDefinition.objects.none()
        return ReportDefinition.objects.filter(allowed_roles=self.role, is_active=True)

    @property
    def can_view_reports(self) -> bool:
        """True if the user has at least one accessible report."""
        from .reports import ReportDefinition

        if self.user.is_staff:
            return ReportDefinition.objects.filter(is_active=True).exists()
        return self.get_allowed_reports().exists()

    def get_allowed_dashboards(self) -> models.QuerySet[Any]:
        """Get dashboards the user can access via their role."""
        from .dashboards import Dashboard

        if self.user.is_staff:
            return Dashboard.objects.filter(is_active=True)
        if not self.role:
            return Dashboard.objects.none()
        return Dashboard.objects.filter(allowed_roles=self.role, is_active=True)

    @property
    def can_view_dashboards(self) -> bool:
        """True if the user has at least one accessible dashboard."""
        from .dashboards import Dashboard

        if self.user.is_staff:
            return Dashboard.objects.filter(is_active=True).exists()
        return self.get_allowed_dashboards().exists()

    def get_allowed_tethers(self) -> models.QuerySet[Any]:
        """Get tethers the user can access via their role."""
        from .tethers import Tether

        if self.user.is_staff:
            return Tether.objects.filter(is_active=True)
        if not self.role:
            return Tether.objects.none()
        return Tether.objects.filter(allowed_roles=self.role, is_active=True)

    @property
    def can_view_tethers(self) -> bool:
        """True if the user has at least one accessible tether."""
        from .tethers import Tether

        if self.user.is_staff:
            return Tether.objects.filter(is_active=True).exists()
        if not self.role or not self.role.can_view_tethers:
            return False
        return self.get_allowed_tethers().exists()

    def get_allowed_reports_names(self) -> set[str] | None:
        """Get report names accessible to this user for MCP filter registration.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the user has no reports assigned.
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        return set(self.get_allowed_reports().values_list("name", flat=True))

    def get_allowed_dashboards_names(self) -> set[str] | None:
        """Get dashboard names accessible to this user for MCP filter registration.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the user has no dashboards assigned.
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        return set(self.get_allowed_dashboards().values_list("name", flat=True))

    def get_allowed_tethers_ids(self) -> set[str] | None:
        """Get tether IDs (as strings) accessible to this user for MCP filter registration.

        Returns None if the user is unrestricted (staff or admin role).
        Returns an empty set when the user has no tethers assigned.
        Uses IDs rather than names because tether names are not unique.
        """
        if self.user.is_staff or (self.role and self.role.is_admin_role):
            return None
        return {str(pk) for pk in self.get_allowed_tethers().values_list("id", flat=True)}

    @property
    def can_view_docs(self) -> bool:
        """True if the user has at least one accessible documentation source."""
        if self.user.is_staff:
            return DocumentationSource.objects.filter(is_active=True).exists()
        result = self.get_allowed_doc_sources()
        return result is None or bool(result)

    @property
    def can_chat(self) -> bool:
        """True if the user is allowed to use the chat interface."""
        if self.user.is_staff:
            return True
        if not self.role:
            return False
        if self.role.is_admin_role:
            return True
        return self.role.can_chat
