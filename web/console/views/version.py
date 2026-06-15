"""Version & updates console tab.

Shows the running TetherDust product version, the latest release found by the
update-check task, an update-available indicator, and per-version release notes
read from the repo-root ``changelog/`` directory.
"""

import markdown
from core.models import SystemConfiguration
from core.version import (
    LATEST_CHECKED_AT_KEY,
    LATEST_RELEASE_URL_KEY,
    changelog_entries,
    current_version,
    latest_version,
    update_available,
)
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from console.views._helpers import staff_required


@staff_required
def version_view(request: HttpRequest) -> HttpResponse:
    current = current_version()

    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc"])
    entries = []
    for entry in changelog_entries():
        md.reset()
        entries.append(
            {
                "version": entry["version"],
                "html": md.convert(entry["raw"]),
                "is_current": entry["version"] == current,
            }
        )

    return render(
        request,
        "console/version.html",
        {
            "section": "version",
            "current_version": current,
            "latest_version": latest_version(),
            "update_available": update_available(),
            "latest_release_url": SystemConfiguration.get_value(LATEST_RELEASE_URL_KEY, ""),
            "latest_checked_at": SystemConfiguration.get_value(LATEST_CHECKED_AT_KEY, ""),
            "changelog_entries": entries,
        },
    )
