"""Admin Version console API: running release, update status, and changelog.

Ports the legacy ``version_view`` (``management/views/version.py``). Changelog
entries are returned as raw markdown (``raw``) so the SPA renders them
client-side instead of the server pre-rendering HTML.
"""

from __future__ import annotations

from engine.services import SystemConfigService, get
from engine.version import (
    LATEST_CHECKED_AT_KEY,
    LATEST_RELEASE_URL_KEY,
    changelog_entries,
    current_version,
    latest_version,
    update_available,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsStaffUser


class VersionView(APIView):
    """Running product version, update availability, and per-version release notes."""

    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        current = current_version()
        cfg = get(SystemConfigService)
        entries = [
            {
                "version": entry["version"],
                "raw": entry["raw"],
                "is_current": entry["version"] == current,
            }
            for entry in changelog_entries()
        ]
        return Response(
            {
                "current_version": current,
                "latest_version": latest_version(),
                "update_available": update_available(),
                "latest_release_url": cfg.get_value(LATEST_RELEASE_URL_KEY, ""),
                "latest_checked_at": cfg.get_value(LATEST_CHECKED_AT_KEY, ""),
                "changelog_entries": entries,
            }
        )
