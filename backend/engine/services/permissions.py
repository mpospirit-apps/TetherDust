"""Permission service.

Resolves what a user may access from their :class:`UserProfile` + :class:`Role`.
A ``None`` return from the ``get_allowed_*`` methods means "unrestricted" (staff
or an admin role); an empty set/queryset means "no access".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models

from ..models.connections import DocumentationSource, MCPServerConfiguration

if TYPE_CHECKING:
    from ..models.auth import UserProfile


class PermissionService:
    """Access-control queries for a user profile."""

    def _unrestricted(self, profile: UserProfile) -> bool:
        return bool(profile.user.is_staff or (profile.role and profile.role.is_admin_role))

    def get_max_row_limit(self, profile: UserProfile) -> int | None:
        """User's maximum row limit. None for staff (no limit)."""
        if profile.user.is_staff:
            return None
        return profile.role.max_row_limit if profile.role else 100

    def get_allowed_tools(self, profile: UserProfile) -> set[str] | None:
        """Tool names the user can access (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        if not profile.role:
            return set()
        return set(
            profile.role.allowed_tools.filter(
                is_enabled=True, mcp_server__is_active=True
            ).values_list("tool_name", flat=True)
        )

    def get_allowed_databases(self, profile: UserProfile) -> set[str] | None:
        """Database names the user can access (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        if not profile.role:
            return set()
        return set(
            profile.role.allowed_databases.filter(is_active=True).values_list("name", flat=True)
        )

    def get_allowed_doc_sources(self, profile: UserProfile) -> set[str] | None:
        """Documentation source names the user can access (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        if not profile.role:
            return set()
        return set(
            profile.role.allowed_doc_sources.filter(is_active=True).values_list(
                "folder_name", flat=True
            )
        )

    def get_allowed_codebases(self, profile: UserProfile) -> set[str] | None:
        """Codebase names the user can access (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        if not profile.role:
            return set()
        return set(
            profile.role.allowed_codebases.filter(is_active=True).values_list("name", flat=True)
        )

    def get_allowed_prompts(self, profile: UserProfile) -> set[str] | None:
        """Prompt names the user can access (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        if not profile.role:
            return set()
        return set(
            profile.role.allowed_prompts.filter(
                is_enabled=True, mcp_server__is_active=True
            ).values_list("prompt_name", flat=True)
        )

    def get_allowed_mcp_servers(
        self, profile: UserProfile
    ) -> models.QuerySet[MCPServerConfiguration]:
        """Active non-built-in MCP servers the user's role may use."""
        if profile.user.is_staff:
            return MCPServerConfiguration.objects.filter(is_active=True, is_builtin=False)
        if not profile.role:
            return MCPServerConfiguration.objects.none()
        return profile.role.allowed_mcp_servers.filter(is_active=True, is_builtin=False)

    def get_allowed_reports(self, profile: UserProfile) -> models.QuerySet[Any]:
        """Report definitions the user can access via their role."""
        from ..models.reports import ReportDefinition

        if profile.user.is_staff:
            return ReportDefinition.objects.filter(is_active=True)
        if not profile.role:
            return ReportDefinition.objects.none()
        return ReportDefinition.objects.filter(allowed_roles=profile.role, is_active=True)

    def can_view_reports(self, profile: UserProfile) -> bool:
        """True if the user has at least one accessible report."""
        return self.get_allowed_reports(profile).exists()

    def get_allowed_dashboards(self, profile: UserProfile) -> models.QuerySet[Any]:
        """Dashboards the user can access via their role."""
        from ..models.dashboards import Dashboard

        if profile.user.is_staff:
            return Dashboard.objects.filter(is_active=True)
        if not profile.role:
            return Dashboard.objects.none()
        return Dashboard.objects.filter(allowed_roles=profile.role, is_active=True)

    def can_view_dashboards(self, profile: UserProfile) -> bool:
        """True if the user has at least one accessible dashboard."""
        return self.get_allowed_dashboards(profile).exists()

    def get_allowed_tethers(self, profile: UserProfile) -> models.QuerySet[Any]:
        """Tethers the user can access via their role."""
        from ..models.tethers import Tether

        if profile.user.is_staff:
            return Tether.objects.filter(is_active=True)
        if not profile.role:
            return Tether.objects.none()
        return Tether.objects.filter(allowed_roles=profile.role, is_active=True)

    def can_view_tethers(self, profile: UserProfile) -> bool:
        """True if the user has at least one accessible tether and the role allows it."""
        if profile.user.is_staff:
            return self.get_allowed_tethers(profile).exists()
        if not profile.role or not profile.role.can_view_tethers:
            return False
        return self.get_allowed_tethers(profile).exists()

    def get_allowed_reports_names(self, profile: UserProfile) -> set[str] | None:
        """Report names for MCP filter registration (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        return set(self.get_allowed_reports(profile).values_list("name", flat=True))

    def get_allowed_dashboards_names(self, profile: UserProfile) -> set[str] | None:
        """Dashboard names for MCP filter registration (None = unrestricted)."""
        if self._unrestricted(profile):
            return None
        return set(self.get_allowed_dashboards(profile).values_list("name", flat=True))

    def get_allowed_tethers_ids(self, profile: UserProfile) -> set[str] | None:
        """Tether IDs (as strings) for MCP filter registration (None = unrestricted).

        Uses IDs rather than names because tether names are not unique.
        """
        if self._unrestricted(profile):
            return None
        return {str(pk) for pk in self.get_allowed_tethers(profile).values_list("id", flat=True)}

    def can_view_docs(self, profile: UserProfile) -> bool:
        """True if the user has at least one accessible documentation source."""
        if profile.user.is_staff:
            return DocumentationSource.objects.filter(is_active=True).exists()
        result = self.get_allowed_doc_sources(profile)
        return result is None or bool(result)

    def can_chat(self, profile: UserProfile) -> bool:
        """True if the user is allowed to use the chat interface."""
        if profile.user.is_staff:
            return True
        if not profile.role:
            return False
        if profile.role.is_admin_role:
            return True
        return profile.role.can_chat
