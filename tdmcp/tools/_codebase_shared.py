"""Shared helpers for codebase tools.

Loads ``Codebase`` rows from the admin database (the ``mcp`` container has no
Django but can reach the shared DB via ``ADMIN_DATABASE_URL``), decrypts the
GitHub token, and exposes per-request access control mirroring the doc-source
helpers in ``_db_shared.py``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from ._db_shared import get_allowed_codebases  # re-exported for tools

logger = logging.getLogger(__name__)

__all__ = ["CodebaseConfig", "get_allowed_codebases", "load_codebases", "get_codebase"]


@dataclass
class CodebaseConfig:
    name: str
    repo_url: str
    provider: str = "github"
    local_root: str = ""
    default_branch: str = ""
    cached_tree: list[dict[str, Any]] = field(default_factory=list)
    access_token: str = ""

    @property
    def ref(self) -> str:
        return self.default_branch or "main"


def _decrypt(value: str) -> str:
    """Decrypt a Fernet token using TETHERDUST_ENCRYPTION_KEY (no-op if unset)."""
    if not value:
        return value
    key = os.environ.get("TETHERDUST_ENCRYPTION_KEY", "")
    if not key:
        return value
    try:
        from cryptography.fernet import Fernet, InvalidToken

        try:
            return Fernet(key.encode()).decrypt(value.encode()).decode()
        except InvalidToken:
            return value  # legacy/plaintext
    except ImportError:
        return value


def load_codebases() -> list[CodebaseConfig]:
    """Load active codebases from the admin DB. Returns [] if unavailable."""
    db_url = os.environ.get("ADMIN_DATABASE_URL", "").strip()
    if not db_url:
        return []
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT name, repo_url, provider, local_root, "
                    "default_branch, cached_tree, access_token "
                    "FROM engine_codebase WHERE is_active = true ORDER BY name"
                )
            ).fetchall()
        engine.dispose()
    except Exception as exc:
        logger.warning("Failed to load codebases from ADMIN_DATABASE_URL: %s", exc)
        return []

    result: list[CodebaseConfig] = []
    for row in rows:
        result.append(
            CodebaseConfig(
                name=row.name,
                repo_url=row.repo_url or "",
                provider=row.provider or "github",
                local_root=row.local_root or "",
                default_branch=row.default_branch or "",
                cached_tree=row.cached_tree or [],
                access_token=_decrypt(row.access_token or ""),
            )
        )
    return result


def get_codebase(name: str) -> CodebaseConfig | None:
    """Look up a single codebase by name, honoring the per-request allow-list.

    Returns None if the codebase does not exist or is not allowed for the role.
    """
    allowed = get_allowed_codebases()
    if allowed is not None and name not in allowed:
        return None
    for cb in load_codebases():
        if cb.name == name:
            return cb
    return None
