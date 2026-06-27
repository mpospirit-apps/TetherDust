"""Role admin API: CRUD over roles + the option lists for the access grants.

Manages the six forward M2M grants on the Role model (tools, databases,
doc_sources, codebases, prompts, mcp_servers). Dashboards/reports/tethers access
is the reverse `allowed_roles` relation and is managed from those resources'
admin (added with their feature verticals).
"""

from __future__ import annotations

from typing import Any

from engine.models import (
    Codebase,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    Role,
    ToolConfiguration,
)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser
from api.serializer_meta import SerializerMeta


class RoleSerializer(serializers.ModelSerializer[Role]):
    class Meta(SerializerMeta):
        model = Role
        fields = [
            "id",
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
            "allowed_mcp_servers",
        ]

    def _sync_staff(self, role: Role) -> None:
        """Keep non-superusers' staff flag aligned with the role's admin flag."""
        from django.contrib.auth.models import User

        User.objects.filter(profile__role=role, is_superuser=False).update(
            is_staff=role.is_admin_role
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
    permission_classes = [IsStaffUser]
    queryset = Role.objects.all()
    serializer_class = RoleSerializer

    @action(detail=False, methods=["get"])
    def grants(self, request: Request) -> Response:
        """Choices for the role editor's access-grant multi-selects."""
        return Response(
            {
                "tools": [
                    {"id": t.pk, "name": t.tool_name, "mcp_server": t.mcp_server_id}
                    for t in ToolConfiguration.objects.all()
                ],
                "prompts": [
                    {
                        "id": p.pk,
                        "name": p.display_name or p.prompt_name,
                        "mcp_server": p.mcp_server_id,
                    }
                    for p in PromptConfiguration.objects.all()
                ],
                "databases": [
                    {"id": d.pk, "name": d.name} for d in DatabaseConnection.objects.all()
                ],
                "doc_sources": [
                    {"id": s.pk, "name": s.folder_name} for s in DocumentationSource.objects.all()
                ],
                "codebases": [{"id": c.pk, "name": c.name} for c in Codebase.objects.all()],
                "mcp_servers": [
                    {"id": m.pk, "name": m.name}
                    for m in MCPServerConfiguration.objects.filter(is_active=True, is_builtin=False)
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
