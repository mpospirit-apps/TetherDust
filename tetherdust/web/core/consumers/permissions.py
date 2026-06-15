"""Role/profile permission lookups for `ChatConsumer`."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from channels.db import database_sync_to_async

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser, User

    from ..models import UserProfile

    class _Base:
        user: User | AnonymousUser
        profile: UserProfile | None
else:
    _Base = object


class PermissionsMixin(_Base):
    """Async lookups for tools, databases, doc sources, MCP servers, etc.

    Expects ``self.user`` and ``self.profile`` on the consumer.
    """

    @database_sync_to_async
    def _get_user_profile(self) -> UserProfile | None:
        from django.contrib.auth.models import User

        from ..models import UserProfile

        if not isinstance(self.user, User):
            return None
        try:
            return UserProfile.objects.select_related("role").get(user=self.user)
        except UserProfile.DoesNotExist:
            return None

    @database_sync_to_async
    def _user_can_chat(self) -> bool:
        if self.user.is_staff:
            return True
        return bool(self.profile and self.profile.can_chat)

    @database_sync_to_async
    def _get_allowed_tools(self) -> set[str]:
        if not self.profile:
            return set()
        return self.profile.get_allowed_tools() or set()

    @database_sync_to_async
    def _get_all_enabled_tools(self) -> list[str]:
        from ..models import ToolConfiguration

        return list(
            ToolConfiguration.objects.filter(
                is_enabled=True, mcp_server__is_active=True
            ).values_list("tool_name", flat=True)
        )

    @database_sync_to_async
    def _get_allowed_databases(self) -> set[str]:
        if not self.profile:
            return set()
        return self.profile.get_allowed_databases() or set()

    @database_sync_to_async
    def _get_allowed_doc_sources(self) -> set[str] | None:
        """Staff users bypass role filtering (matches doc_sources_api_view)."""
        if self.user.is_staff:
            return None
        if not self.profile:
            return set()
        return self.profile.get_allowed_doc_sources()

    @database_sync_to_async
    def _get_allowed_codebases(self) -> set[str] | None:
        """Staff users bypass role filtering (matches other source lookups)."""
        if self.user.is_staff:
            return None
        if not self.profile:
            return set()
        return self.profile.get_allowed_codebases()

    @database_sync_to_async
    def _get_allowed_reports(self) -> set[str] | None:
        """Staff and admin-role users bypass filtering (return None = unrestricted)."""
        if self.user.is_staff:
            return None
        if not self.profile:
            return set()
        return self.profile.get_allowed_reports_names()

    @database_sync_to_async
    def _get_allowed_dashboards(self) -> set[str] | None:
        """Staff and admin-role users bypass filtering (return None = unrestricted)."""
        if self.user.is_staff:
            return None
        if not self.profile:
            return set()
        return self.profile.get_allowed_dashboards_names()

    @database_sync_to_async
    def _get_allowed_tethers(self) -> set[str] | None:
        """Staff and admin-role users bypass filtering (return None = unrestricted)."""
        if self.user.is_staff:
            return None
        if not self.profile:
            return set()
        return self.profile.get_allowed_tethers_ids()

    @database_sync_to_async
    def _get_allowed_mcp_servers(self) -> list[dict[str, object]]:
        """Return custom MCP server dicts the user may access.

        The built-in server is excluded — it's always available and the
        Codex wrapper renders its config block regardless. Each entry
        decrypts ``auth_token`` so the wrapper can inject it as a header.
        """
        if not self.profile:
            return []
        from ..models import SystemConfiguration

        servers = self.profile.get_allowed_mcp_servers()
        result: list[dict[str, object]] = []
        local_mcp_base = SystemConfiguration.get_value("local_mcp_base_url", "") or os.environ.get(
            "LOCAL_MCP_BASE_URL", "http://local-mcp:8003"
        )
        for server in servers:
            if server.is_local:
                result.append(
                    {
                        "name": server.name,
                        "url": f"{local_mcp_base.rstrip('/')}/mcp/{server.id}/",
                        "transport": "streamable-http",
                        "auth_token": None,
                        "headers": {},
                    }
                )
            elif server.url:
                result.append(
                    {
                        "name": server.name,
                        "url": server.url,
                        "transport": server.transport or "streamable-http",
                        "auth_token": server.auth_token,
                        "headers": server.headers or {},
                    }
                )
        return result

    @database_sync_to_async
    def _get_max_row_limit(self) -> int | None:
        from ..models import SystemConfiguration

        system_default = cast(int | None, SystemConfiguration.get_value("max_row_limit", 100))
        if not self.profile:
            return system_default
        return self.profile.get_max_row_limit()
