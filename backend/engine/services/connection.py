"""Database connection and codebase services."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings

from ..integrations.github_client import parse_owner_repo
from ..integrations.gitlab_client import parse_gitlab_path
from ..models.connections import Codebase, DatabaseConnection, DocumentationSource

_SQLALCHEMY_DRIVERS: dict[str, str] = {
    "postgresql": "postgresql+psycopg2",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pymssql",
    "sqlite": "sqlite",
    "mariadb": "mariadb+pymysql",
    "clickhouse": "clickhouse+connect",
}


class ConnectionService:
    """Operations on :class:`DatabaseConnection`."""

    def get_connection_url(self, conn: DatabaseConnection) -> str:
        """Build the SQLAlchemy connection URL for a connection."""
        if conn.connection_string:
            return conn.connection_string

        driver = _SQLALCHEMY_DRIVERS.get(conn.engine, conn.engine)
        if conn.engine == "sqlite":
            return f"sqlite:///{conn.database}"

        port_str = f":{conn.port}" if conn.port else ""
        password = quote_plus(conn.password) if conn.password else ""
        auth = f"{conn.username}:{password}@" if conn.username else ""
        return f"{driver}://{auth}{conn.host}{port_str}/{conn.database}"

    def list_sqlite_files(self) -> list[dict[str, str]]:
        """Files under the SQLite directory, for the file-path picker."""
        base = Path(settings.TETHERDUST_DATABASES_DIR)
        files: list[dict[str, str]] = []
        if base.exists() and base.is_dir():
            for entry in sorted(base.rglob("*")):
                if entry.is_file() and not any(
                    part.startswith(".") for part in entry.relative_to(base).parts
                ):
                    files.append({"name": str(entry.relative_to(base)), "path": str(entry)})
        return files


class CodebaseService:
    """Operations on :class:`Codebase`."""

    def owner_repo(self, codebase: Codebase) -> tuple[str, str]:
        """Parse ``repo_url`` into (owner, repo) for GitHub. Raises ValueError if invalid."""
        return parse_owner_repo(codebase.repo_url)

    def project_path(self, codebase: Codebase) -> str:
        """Parse ``repo_url`` into a GitLab project path. Raises ValueError if invalid."""
        return parse_gitlab_path(codebase.repo_url)

    def ref(self, codebase: Codebase) -> str:
        """Branch the agent should read: explicit branch, else default, else 'main'."""
        return codebase.branch or codebase.default_branch or "main"

    def effective_exclude_globs(self, codebase: Codebase) -> list[str]:
        """Configured excludes, or the default set when none are configured."""
        return codebase.exclude_globs or Codebase.DEFAULT_EXCLUDE_GLOBS

    def ccc_project(self, codebase: Codebase) -> str:
        """ccc project path (relative to the ccc ``/app`` mount) for a local codebase.

        Kept in sync with the tdmcp-side ``_codebase_local.ccc_project`` so search
        hits resolve against the same root the browse tools read from.
        """
        project = "sources/codebases/" + codebase.local_root.strip("/")
        if codebase.subpath:
            project += "/" + codebase.subpath.strip("/")
        return project


class DocSourceService:
    """Operations on :class:`DocumentationSource`."""

    def resolved_path(self, source: DocumentationSource) -> str:
        """Absolute path by joining the documentations dir with the folder name."""
        return str(Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / source.folder_name)

    def sync_from_filesystem(self) -> dict[str, list[str]]:
        """Auto-discover top-level folders in documentations/ and sync to DB.

        Creates a source for any folder not yet in the DB, reactivates sources
        whose folder reappeared, and deactivates sources whose folder is gone.
        Returns a dict with 'created' and 'deactivated' folder-name lists.
        """
        import logging

        logger = logging.getLogger(__name__)
        docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
        result: dict[str, list[str]] = {"created": [], "deactivated": []}

        if not docs_dir.exists() or not docs_dir.is_dir():
            logger.warning("Documentations directory not found: %s", docs_dir)
            return result

        disk_folders = {
            entry.name
            for entry in docs_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        }

        existing = set(DocumentationSource.objects.values_list("folder_name", flat=True))
        for folder_name in sorted(disk_folders - existing):
            DocumentationSource.objects.create(folder_name=folder_name)
            result["created"].append(folder_name)
            logger.info("Auto-created documentation source: %s", folder_name)

        DocumentationSource.objects.filter(folder_name__in=disk_folders, is_active=False).update(
            is_active=True
        )

        missing = existing - disk_folders
        if missing:
            DocumentationSource.objects.filter(folder_name__in=missing, is_active=True).update(
                is_active=False
            )
            result["deactivated"] = sorted(missing)
            for name in result["deactivated"]:
                logger.info("Deactivated documentation source (folder removed): %s", name)

        return result
