"""Database connection admin API: CRUD + connectivity test + engine metadata."""

from __future__ import annotations

from engine.models import DatabaseConnection
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import IsStaffUser

from .serializers import DatabaseConnectionSerializer


class DatabaseConnectionViewSet(viewsets.ModelViewSet[DatabaseConnection]):
    """Staff CRUD for database connections, plus `engines` metadata and `test`."""

    permission_classes = [IsStaffUser]
    queryset = DatabaseConnection.objects.all()
    serializer_class = DatabaseConnectionSerializer

    @action(detail=False, methods=["get"])
    def engines(self, request: Request) -> Response:
        """Engine choices + default ports for the add/edit form."""
        return Response(
            {
                "choices": [
                    {"value": value, "label": label}
                    for value, label in DatabaseConnection.ENGINE_CHOICES
                ],
                "default_ports": DatabaseConnection.DEFAULT_PORTS,
            }
        )

    @action(detail=True, methods=["post"])
    def test(self, request: Request, pk: str | None = None) -> Response:
        """Probe connectivity (mirrors the legacy `database_test_view`)."""
        from engine.engines.db_runner import ping

        obj = self.get_object()
        try:
            ping(obj)
            return Response({"ok": True, "detail": "Connected"})
        except Exception as exc:
            return Response({"ok": False, "detail": str(exc)})
