"""TetherDust product release version + update-availability helpers.

The product version is the repo-root ``VERSION`` file (matched to the git tag),
*not* the ``mcp_server`` package version in ``pyproject.toml`` — those track
different things. The "latest available" version is polled from GitHub Releases
by ``core.tasks.check_for_updates`` and cached in ``SystemConfiguration``.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path

from django.conf import settings
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

GITHUB_REPOSITORY = "mpospirit-apps/TetherDust"

# SystemConfiguration keys written by the update-check task.
LATEST_VERSION_KEY = "latest_version"
LATEST_RELEASE_URL_KEY = "latest_release_url"
LATEST_CHECKED_AT_KEY = "latest_version_checked_at"


def _repo_root() -> Path:
    # BASE_DIR is <root>/tetherdust/web both in the image (/app/tetherdust/web)
    # and in a local checkout, so the repo root is two levels up.
    return Path(settings.BASE_DIR).parents[1]


@functools.lru_cache(maxsize=1)
def current_version() -> str:
    """Running product version from the repo-root ``VERSION`` file.

    Cached for the process lifetime — ``VERSION`` only changes on a rebuild.
    Returns ``"unknown"`` if the file is missing (e.g. a misbuilt image) rather
    than raising, so the console page still renders.
    """
    try:
        return (_repo_root() / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        logger.warning("VERSION file not found at repo root; reporting 'unknown'")
        return "unknown"


def changelog_entries() -> list[dict[str, str]]:
    """Per-version release notes from the repo-root ``changelog/`` directory.

    Each ``<version>.md`` file is one release (e.g. ``0.2.0.md``); the filename
    is the version. Returns ``[{"version", "raw"}]`` sorted newest-first. Files
    whose name does not parse as a version (e.g. ``README.md``) are skipped, so
    the directory can hold docs alongside the notes.

    Not cached: admins may add/edit notes between releases and expect to see
    them without a restart (in the image the files are static, so it is cheap).
    """
    directory = _repo_root() / "changelog"
    if not directory.is_dir():
        return []

    entries: list[tuple[Version, str, str]] = []
    for path in directory.glob("*.md"):
        try:
            parsed = Version(_normalize(path.stem))
        except InvalidVersion:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        entries.append((parsed, _normalize(path.stem), raw))

    entries.sort(key=lambda e: e[0], reverse=True)
    return [{"version": version, "raw": raw} for _, version, raw in entries]


def latest_version() -> str:
    """Latest release tag cached by the update-check task (``""`` if unknown)."""
    from core.models import SystemConfiguration

    return (SystemConfiguration.get_value(LATEST_VERSION_KEY, "") or "").strip()


def _normalize(tag: str) -> str:
    return tag.strip().lstrip("vV")


def update_available() -> bool:
    """True when a cached release tag parses as strictly newer than the running
    version. Any unparseable/missing value yields ``False`` (fail quiet)."""
    latest = latest_version()
    if not latest:
        return False
    try:
        return Version(_normalize(latest)) > Version(_normalize(current_version()))
    except InvalidVersion:
        logger.warning(
            "Could not compare versions: current=%r latest=%r", current_version(), latest
        )
        return False
