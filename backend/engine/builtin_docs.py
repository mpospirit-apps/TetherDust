"""Register filesystem documentation folders on startup (post_migrate).

Documentation sources are normally discovered lazily by
``get(DocSourceService).sync_from_filesystem()`` when a staff user opens the
management docsources list. That means a folder dropped into ``sources/docs/``
(including the docs that ship with TetherDust) stays invisible — to everyone —
until someone happens to open that page.

This module closes that gap: a ``post_migrate`` hook (wired in ``engine/apps.py``)
registers the shipped documentation as a ``Manual`` source and runs a full
filesystem sync so any manually-added folder is registered on boot. Admins/staff
see registered sources immediately; non-admins still need a role grant.
"""

from __future__ import annotations

from engine.services import DocSourceService, get

# Folder name (under sources/docs/) of the docs that ship with the app.
SHIPPED_DOC_FOLDER = "TetherDust Documentation"
SHIPPED_DOC_DESCRIPTION = (
    "Official TetherDust product documentation — features, agent integrations, "
    "and usage guides that ship with the app."
)


def ensure_shipped_docs(using: str | None = None) -> None:
    """Register the shipped docs (as Manual) and sync filesystem folders.

    Create-only for the shipped source: its type is set to Manual on first
    registration and never overwritten, so a later admin change survives. Safe to
    call repeatedly (e.g. from post_migrate). No-ops if the tables do not exist
    yet or on non-default DB aliases (e.g. test setup).
    """
    from pathlib import Path

    from django.conf import settings
    from django.db import DEFAULT_DB_ALIAS
    from django.db.utils import OperationalError, ProgrammingError

    from .models import DocumentationSource

    db = using or DEFAULT_DB_ALIAS
    if db != DEFAULT_DB_ALIAS:
        return

    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)

    try:
        # Create the shipped source first, as Manual, so the subsequent sync
        # (which defaults new sources to DATABASE) leaves its type alone.
        if (docs_dir / SHIPPED_DOC_FOLDER).is_dir():
            DocumentationSource.objects.get_or_create(
                folder_name=SHIPPED_DOC_FOLDER,
                defaults={
                    "doc_type": DocumentationSource.DocType.MANUAL,
                    "description": SHIPPED_DOC_DESCRIPTION,
                    "is_active": True,
                },
            )

        # Register any other folders present on disk (and reactivate/deactivate
        # per the filesystem), so manual additions appear without a page visit.
        get(DocSourceService).sync_from_filesystem()
    except (OperationalError, ProgrammingError):
        # Tables not migrated yet (mid-bootstrap). The next migrate run will
        # fire post_migrate again once the schema exists.
        pass
