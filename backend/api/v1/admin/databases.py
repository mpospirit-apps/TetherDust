"""Database connection admin API: CRUD + connectivity test + engine metadata."""

from __future__ import annotations

from engine.models import DatabaseConnection
from engine.services import ConnectionService, get
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

    @action(detail=False, methods=["get"], url_path="sqlite-files")
    def sqlite_files(self, request: Request) -> Response:
        """Files under sources/databases/, for the SQLite file-path dropdown."""
        used_by = dict(
            DatabaseConnection.objects.filter(engine="sqlite").values_list("database", "name")
        )
        files = get(ConnectionService).list_sqlite_files()
        return Response({"files": [{**f, "used_by": used_by.get(f["path"])} for f in files]})

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

    @action(detail=False, methods=["post"], url_path="test")
    def test_draft(self, request: Request) -> Response:
        """Probe connectivity for unsaved add/edit form values.

        A blank ``password`` falls back to the stored credential when an
        existing connection ``id`` is supplied, mirroring the "leave blank to
        keep existing" behaviour of the update serializer. ``name`` is
        dropped before validation: it has no bearing on connectivity, and
        Save already enforces it separately, so testing shouldn't require
        one to be typed (or fail on a not-yet-unique one) first.
        """
        from engine.engines.db_runner import ping

        existing = None
        if obj_id := request.data.get("id"):
            existing = DatabaseConnection.objects.filter(pk=obj_id).first()

        draft_data = {k: v for k, v in request.data.items() if k != "name"}
        serializer = DatabaseConnectionSerializer(instance=existing, data=draft_data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        password = data.pop("password", "")
        instance = DatabaseConnection(**data)
        if password:
            instance.password = password
        elif existing is not None:
            instance.password = existing.password

        try:
            ping(instance)
            return Response({"ok": True, "detail": "Connected"})
        except Exception as exc:
            return Response({"ok": False, "detail": str(exc)})
