"""Role admin API: CRUD over roles + the option lists for the access grants.

Manages the six forward M2M grants on the Role model (tools, databases,
doc_sources, codebases, prompts, mcp_servers) plus reports, dashboards and
tethers, which are the reverse side of each one's ``allowed_roles`` — so they
can be shared from either the role form or their own.

Any staff user may read roles — the dashboard, report and tether forms pick
from them. Changing one is user management (its grants and admin flag decide
what every user holding it can reach), so writes need ``CanManageUsers``, the
same gate as the user admin API.
"""

from __future__ import annotations

from typing import Any

from engine.models import (
    Codebase,
    Dashboard,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    ReportDefinition,
    Role,
    Tether,
    ToolConfiguration,
)
from engine.services import ToolService, get
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import CanManageUsers, IsStaffUser
from api.serializer_meta import SerializerMeta


class RoleSerializer(serializers.ModelSerializer[Role]):
    # Reverse sides of each resource's ``allowed_roles``; declared so they
    # aren't required.
    allowed_reports = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ReportDefinition.objects.all(), required=False
    )
    allowed_dashboards = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Dashboard.objects.all(), required=False
    )
    allowed_tethers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tether.objects.all(), required=False
    )

    class Meta(SerializerMeta):
        model = Role
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "can_chat",
            "can_manage_users",
            "is_admin_role",
            "max_row_limit",
            "allowed_tools",
            "allowed_databases",
            "allowed_doc_sources",
            "allowed_codebases",
            "allowed_prompts",
            "allowed_mcp_servers",
            "allowed_reports",
            "allowed_dashboards",
            "allowed_tethers",
        ]

    def _sync_staff(self, role: Role) -> None:
        """Keep non-superusers' staff flag aligned with whether the role grants admin."""
        from django.contrib.auth.models import User

        User.objects.filter(profile__role=role, is_superuser=False).update(
            is_staff=role.grants_admin
        )

    def create(self, validated_data: Any) -> Role:
        role = super().create(validated_data)
        self._sync_staff(role)
        return role

    def update(self, instance: Role, validated_data: Any) -> Role:
        role = super().update(instance, validated_data)
        self._sync_staff(role)
        return role


class RoleViewSet(viewsets.ModelViewSet[Role]):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in SAFE_METHODS:
            return [IsStaffUser()]
        return [CanManageUsers()]

    @action(detail=False, methods=["get"])
    def grants(self, request: Request) -> Response:
        """Choices for the role editor's access-grant multi-selects.

        ``is_active`` mirrors the filter ``PermissionService`` applies, so the
        editor can flag a grant that currently resolves to nothing (an inactive
        database, report, dashboard or tether, a disabled tool, a tool on an
        inactive server). Tools carry their category so the editor can group them.
        """
        tool_service = get(ToolService)
        return Response(
            {
                "tools": [
                    {
                        "id": t.pk,
                        "name": t.tool_name,
                        "mcp_server": t.mcp_server_id,
                        "category_label": tool_service.category_label(t),
                        "is_active": t.is_enabled and t.mcp_server.is_active,
                    }
                    for t in ToolConfiguration.objects.select_related("mcp_server")
                ],
                "prompts": [
                    {
                        "id": p.pk,
                        "name": p.display_name or p.prompt_name,
                        "mcp_server": p.mcp_server_id,
                        "is_active": p.is_enabled and p.mcp_server.is_active,
                    }
                    for p in PromptConfiguration.objects.select_related("mcp_server")
                ],
                "databases": [
                    {"id": d.pk, "name": d.name, "is_active": d.is_active}
                    for d in DatabaseConnection.objects.all()
                ],
                "doc_sources": [
                    {"id": s.pk, "name": s.folder_name, "is_active": s.is_active}
                    for s in DocumentationSource.objects.all()
                ],
                "codebases": [
                    {"id": c.pk, "name": c.name, "is_active": c.is_active}
                    for c in Codebase.objects.all()
                ],
                "mcp_servers": [
                    {"id": m.pk, "name": m.name, "is_active": True}
                    for m in MCPServerConfiguration.objects.filter(is_active=True, is_builtin=False)
                ],
                "reports": [
                    {"id": r.pk, "name": r.name, "is_active": r.is_active}
                    for r in ReportDefinition.objects.all()
                ],
                "dashboards": [
                    {"id": d.pk, "name": d.name, "is_active": d.is_active}
                    for d in Dashboard.objects.all()
                ],
                "tethers": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active}
                    for t in Tether.objects.all()
                ],
            }
        )

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from django.db.models.deletion import ProtectedError

        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        f"Cannot delete role '{instance.name}' — it is assigned to one or more "
                        "users. Reassign them to a different role first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
