"""Database, documentation source, MCP server, tool, prompt, system config, and query audit models."""  # noqa: E501

import json
import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models

from ..integrations.github_client import parse_owner_repo as parse_owner_repo
from ._encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class DatabaseConnection(models.Model):
    """Client-configurable database connection."""

    ENGINE_CHOICES: list[tuple[str, str]] = [
        ("postgresql", "PostgreSQL"),
        ("mysql", "MySQL"),
        ("mssql", "Microsoft SQL Server"),
        ("oracle", "Oracle"),
        ("sqlite", "SQLite"),
        ("mariadb", "MariaDB"),
        ("snowflake", "Snowflake"),
        ("bigquery", "Google BigQuery"),
        ("clickhouse", "ClickHouse"),
    ]

    DEFAULT_PORTS: dict[str, int] = {
        "postgresql": 5432,
        "mysql": 3306,
        "mssql": 1433,
        "oracle": 1521,
        "mariadb": 3306,
        "clickhouse": 8123,
    }

    name = models.CharField(
        max_length=100, unique=True, help_text="Unique identifier for this connection"
    )
    description = models.TextField(
        blank=True, help_text="Helps AI agent understand what data this database contains"
    )
    engine = models.CharField(max_length=50, choices=ENGINE_CHOICES, default="postgresql")
    host = models.CharField(max_length=255, blank=True)
    port = models.IntegerField(null=True, blank=True)
    database = models.CharField(
        max_length=255,
        blank=True,
        help_text="Database name or file path for SQLite. Optional for engines with a default (e.g. ClickHouse uses 'default'), or when using a full connection_string.",  # noqa: E501
    )
    username = models.CharField(max_length=255, blank=True)
    _password = models.CharField(
        max_length=500, blank=True, db_column="password", help_text="Encrypted at rest"
    )
    connection_string = models.TextField(
        blank=True, help_text="Optional: Full SQLAlchemy URL (overrides above fields)"
    )
    extra_options = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional SQLAlchemy connect_args (e.g., SSL settings)",
    )
    read_only = models.BooleanField(
        default=True,
        help_text=(
            "Strongly recommended. Runs every query in a read-only database session on "
            "PostgreSQL, MySQL/MariaDB, SQLite, Oracle, and ClickHouse. SQL Server, "
            "BigQuery, and Snowflake cannot enforce this at the session level — use a "
            "read-only database user / IAM role there. All engines are additionally "
            "checked by the SQL validator."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Database Connection"
        verbose_name_plural = "Database Connections"

    def __str__(self) -> str:
        return f"{self.name} ({self.engine})"

    @property
    def password(self) -> str:
        """Get decrypted password."""
        return decrypt_value(self._password)

    @password.setter
    def password(self, value: str) -> None:
        """Set encrypted password."""
        self._password = encrypt_value(value) if value else ""

    def get_connection_url(self) -> str:
        """Build SQLAlchemy connection URL."""
        if self.connection_string:
            return self.connection_string

        drivers = {
            "postgresql": "postgresql+psycopg2",
            "mysql": "mysql+pymysql",
            "mssql": "mssql+pymssql",
            "oracle": "oracle+cx_oracle",
            "sqlite": "sqlite",
            "mariadb": "mariadb+pymysql",
            "clickhouse": "clickhouse+connect",
        }
        driver = drivers.get(self.engine, self.engine)

        if self.engine == "sqlite":
            return f"sqlite:///{self.database}"

        from urllib.parse import quote_plus

        port_str = f":{self.port}" if self.port else ""
        password = quote_plus(self.password) if self.password else ""
        auth = f"{self.username}:{password}@" if self.username else ""
        return f"{driver}://{auth}{self.host}{port_str}/{self.database}"


class Codebase(models.Model):
    """Client-configurable source-code repository the agent reads on demand.

    A codebase is a first-class "source" alongside databases and documentation:
    the agent browses and reads its files via the codebase MCP tools, and roles
    grant access through ``Role.allowed_codebases``. v1 supports GitHub via the
    REST API (no clone); contents are fetched live and the file tree is cached
    on sync.
    """

    PROVIDER_CHOICES: list[tuple[str, str]] = [("github", "GitHub")]

    SYNC_PENDING: str = "pending"
    SYNC_SYNCING: str = "syncing"
    SYNC_OK: str = "ok"
    SYNC_ERROR: str = "error"
    SYNC_STATUS_CHOICES: list[tuple[str, str]] = [
        (SYNC_PENDING, "Pending"),
        (SYNC_SYNCING, "Syncing"),
        (SYNC_OK, "Synced"),
        (SYNC_ERROR, "Error"),
    ]

    # Sensible defaults so the agent isn't flooded with build output / binaries.
    DEFAULT_EXCLUDE_GLOBS: list[str] = [
        "node_modules/*",
        "dist/*",
        "build/*",
        "vendor/*",
        ".git/*",
        "*.lock",
        "*.min.js",
        "*.map",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.svg",
        "*.ico",
        "*.webp",
        "*.pdf",
        "*.zip",
        "*.gz",
        "*.tar",
        "*.woff",
        "*.woff2",
        "*.ttf",
        "*.eot",
    ]

    name = models.CharField(
        max_length=100, unique=True, help_text="Unique identifier for this codebase"
    )
    description = models.TextField(
        blank=True, help_text="Helps the AI agent understand what this repository contains"
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="github")
    repo_url = models.CharField(max_length=500, help_text="e.g. https://github.com/owner/repo")
    branch = models.CharField(
        max_length=255, blank=True, help_text="Leave blank to use the repository's default branch"
    )
    subpath = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional sub-directory to scope to, for monorepos (e.g. services/api)",
    )
    include_globs = models.JSONField(
        default=list,
        blank=True,
        help_text='Glob patterns to include, e.g. ["src/**", "*.py"]. Empty = everything (minus excludes).',  # noqa: E501
    )
    exclude_globs = models.JSONField(
        default=list,
        blank=True,
        help_text="Glob patterns to exclude. Empty = a sensible default set (node_modules, build output, binaries).",  # noqa: E501
    )
    _access_token = models.CharField(
        max_length=500,
        blank=True,
        db_column="access_token",
        help_text="Encrypted GitHub token. Leave blank for public repositories.",
    )
    # Sync / cache state
    default_branch = models.CharField(max_length=255, blank=True, help_text="Resolved on sync")
    cached_tree = models.JSONField(
        default=list,
        blank=True,
        help_text="Cached repository file tree (list of {path, type, size}), refreshed on sync.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default=SYNC_PENDING)
    sync_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Codebase"
        verbose_name_plural = "Codebases"

    def __str__(self) -> str:
        return self.name

    @property
    def access_token(self) -> str:
        """Get decrypted access token."""
        return decrypt_value(self._access_token)

    @access_token.setter
    def access_token(self, value: str) -> None:
        """Set encrypted access token."""
        self._access_token = encrypt_value(value) if value else ""

    def owner_repo(self) -> tuple[str, str]:
        """Parse ``repo_url`` into (owner, repo). Raises ValueError if invalid."""
        return parse_owner_repo(self.repo_url)

    @property
    def ref(self) -> str:
        """Branch the agent should read: explicit branch, else resolved default, else 'main'."""
        return self.branch or self.default_branch or "main"

    @property
    def effective_exclude_globs(self) -> list[str]:
        """Configured excludes, or the default set when none are configured."""
        return self.exclude_globs or self.DEFAULT_EXCLUDE_GLOBS


DOC_TYPE_DESCRIPTIONS: dict[str, str] = {
    "database": "Docs describing database schemas, tables, and query examples",
    "codebase": "Docs about source code, APIs, and modules",
    "manual": "General user/admin manuals, guides, and SOPs",
    "policy": "Compliance rules, business policies, and governance docs",
    "api": "External API references — REST/GraphQL specs, OpenAPI docs",
    "report": "Generated report templates or historical report definitions",
    "ontology": "Domain terminology, glossaries, and taxonomy definitions",
    "runbook": "Operational procedures and incident response playbooks",
}


class DocumentationSource(models.Model):
    """Configurable documentation source for MCP tools.

    Each record maps to a top-level folder inside the documentations/ directory.
    Sources are auto-discovered via sync_from_filesystem() and assigned to roles
    for visibility control.
    """

    class DocType(models.TextChoices):
        DATABASE = "database", "Database"
        CODEBASE = "codebase", "Codebase"
        MANUAL = "manual", "Manual"
        POLICY = "policy", "Policy"
        API = "api", "API"
        REPORT = "report", "Report"
        ONTOLOGY = "ontology", "Ontology"
        RUNBOOK = "runbook", "Runbook"

    folder_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Folder name inside the documentations/ directory",
    )
    doc_type = models.CharField(
        max_length=20,
        choices=DocType.choices,
        default=DocType.DATABASE,
        verbose_name="Type",
        help_text="The category of documentation this source contains",
    )
    description = models.TextField(
        blank=True, help_text="Helps AI understand what this source contains"
    )
    file_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text='Glob patterns for files, e.g. ["*.md"] or ["*.py", "*.sql"]. Leave empty for default (*.md).',  # noqa: E501
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["folder_name"]
        verbose_name = "Documentation Source"
        verbose_name_plural = "Documentation Sources"

    def __str__(self) -> str:
        return self.folder_name

    @property
    def resolved_path(self) -> str:
        """Return absolute path by joining documentations dir with folder_name."""
        from django.conf import settings

        return str(Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / self.folder_name)

    @classmethod
    def sync_from_filesystem(cls) -> dict[str, list[str]]:
        """Auto-discover top-level folders in documentations/ and sync to DB.

        Creates DocumentationSource for any folder not yet in DB.
        Marks sources as inactive if their folder no longer exists.
        Returns dict with 'created' and 'deactivated' folder name lists.
        """
        docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
        result: dict[str, list[str]] = {"created": [], "deactivated": []}

        if not docs_dir.exists() or not docs_dir.is_dir():
            logger.warning("Documentations directory not found: %s", docs_dir)
            return result

        # Discover folders on disk
        disk_folders = {
            entry.name
            for entry in docs_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        }

        # Create missing sources
        existing = set(cls.objects.values_list("folder_name", flat=True))
        for folder_name in sorted(disk_folders - existing):
            cls.objects.create(folder_name=folder_name)
            result["created"].append(folder_name)
            logger.info("Auto-created documentation source: %s", folder_name)

        # Re-activate sources whose folder reappeared
        cls.objects.filter(folder_name__in=disk_folders, is_active=False).update(is_active=True)

        # Deactivate sources whose folder is gone
        missing = existing - disk_folders
        if missing:
            cls.objects.filter(folder_name__in=missing, is_active=True).update(is_active=False)
            result["deactivated"] = sorted(missing)
            for name in result["deactivated"]:
                logger.info("Deactivated documentation source (folder removed): %s", name)

        return result


class MCPServerConfiguration(models.Model):
    """Admin-configurable MCP server grouping for tools."""

    TRANSPORT_CHOICES: list[tuple[str, str]] = [
        ("", "Local (built-in)"),
        ("sse", "SSE"),
        ("streamable-http", "Streamable HTTP"),
    ]

    name = models.CharField(
        max_length=100, unique=True, help_text="Display name for this MCP server"
    )
    description = models.TextField(blank=True, help_text="What this MCP server provides")
    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="Full MCP endpoint URL, e.g. https://example.com/mcp (leave blank for the built-in server)",  # noqa: E501
    )
    host = models.CharField(max_length=255, blank=True, help_text="Deprecated — use `url` instead")
    port = models.IntegerField(null=True, blank=True, help_text="Deprecated — use `url` instead")
    transport = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=TRANSPORT_CHOICES,
        help_text="Transport protocol (leave blank for the built-in server)",
    )
    _auth_token = models.CharField(
        max_length=500,
        blank=True,
        db_column="auth_token",
        help_text="Encrypted bearer token sent as Authorization: Bearer …",
    )
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text='Extra HTTP headers sent to the MCP server, e.g. {"X-API-Key": "abc"}',
    )
    # Local subprocess server fields
    command = models.CharField(
        max_length=500,
        blank=True,
        help_text='Executable to run, e.g. "npx" or "uvx". Set this for local subprocess servers.',
    )
    args = models.JSONField(
        default=list,
        blank=True,
        help_text='Arguments for the command, e.g. ["-y", "@notionhq/notion-mcp-server"]',
    )
    _command_env = models.TextField(
        blank=True,
        db_column="command_env",
        help_text="Encrypted JSON dict of environment variables passed to the subprocess.",
    )
    is_active = models.BooleanField(default=True)
    is_builtin = models.BooleanField(
        default=False, help_text="Built-in servers cannot be edited or deleted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_builtin", "name"]
        verbose_name = "MCP Server"
        verbose_name_plural = "MCP Servers"

    def __str__(self) -> str:
        return self.name

    @property
    def auth_token(self) -> str:
        """Decrypted bearer token."""
        return decrypt_value(self._auth_token)

    @auth_token.setter
    def auth_token(self, value: str) -> None:
        self._auth_token = encrypt_value(value) if value else ""

    @property
    def command_env(self) -> dict[str, str]:
        """Decrypted env vars dict for local subprocess servers."""
        raw = decrypt_value(self._command_env)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return {}
            return {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            return {}

    @command_env.setter
    def command_env(self, value: dict[str, str]) -> None:
        self._command_env = encrypt_value(json.dumps(value)) if value else ""

    @property
    def is_local(self) -> bool:
        """True for local subprocess servers (have a command, not built-in)."""
        return bool(self.command) and not self.is_builtin


class ToolConfiguration(models.Model):
    """Admin-configurable MCP tool settings."""

    # Feature-based grouping for the built-in tools. Custom-server tools are
    # left uncategorized ("" → shown as "Other").
    CATEGORY_CHOICES: list[tuple[str, str]] = [
        ("querying", "Querying"),
        ("docs", "Docs"),
        ("charts", "Charts"),
        ("codebases", "Codebases"),
        ("tethers", "Tethers"),
        ("reports", "Reports"),
    ]

    mcp_server = models.ForeignKey(
        MCPServerConfiguration,
        on_delete=models.CASCADE,
        related_name="tools",
        help_text="MCP server this tool belongs to",
    )
    tool_name = models.CharField(
        max_length=100, unique=True, help_text="Internal tool name (e.g., 'search_docs')"
    )
    display_name = models.CharField(max_length=100, help_text="Human-readable name")
    category = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=CATEGORY_CHOICES,
        help_text="TetherDust feature this tool belongs to (groups tools in the management).",
    )
    description = models.TextField(
        help_text="AI-facing description that guides when/how the tool is used"
    )
    is_enabled = models.BooleanField(default=True)
    input_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text='MCP tool input schema (JSON Schema). Example: {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}',  # noqa: E501
    )
    source_code = models.TextField(
        blank=True,
        default="",
        help_text="Python handler code. Must define an async function handle(arguments: dict) -> str that returns the tool result text.",  # noqa: E501
    )
    settings = models.JSONField(
        default=dict, blank=True, help_text="Tool-specific settings (e.g., max_results, timeout)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "display_name"]
        verbose_name = "Tool Configuration"
        verbose_name_plural = "Tool Configurations"

    def __str__(self) -> str:
        return self.display_name

    @property
    def category_label(self) -> str:
        """Human-readable category, falling back to 'Other' when uncategorized."""
        return self.get_category_display() or "Other"


class PromptConfiguration(models.Model):
    """Admin-configurable MCP prompt template."""

    mcp_server = models.ForeignKey(
        MCPServerConfiguration,
        on_delete=models.CASCADE,
        related_name="prompts",
        help_text="MCP server this prompt belongs to",
    )
    prompt_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Internal prompt name (e.g., 'analyze_table')",
    )
    display_name = models.CharField(
        max_length=100, help_text="Human-readable name shown in autocomplete"
    )
    is_enabled = models.BooleanField(default=True)
    content = models.TextField(
        default="",
        help_text="The prompt instructions. This text is prepended to the user's message as context for the AI agent.",  # noqa: E501
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]
        verbose_name = "Prompt Configuration"
        verbose_name_plural = "Prompt Configurations"

    def __str__(self) -> str:
        return self.display_name


class SystemConfiguration(models.Model):
    """Key-value store for admin-configurable settings."""

    VALUE_TYPE_CHOICES: list[tuple[str, str]] = [
        ("string", "String"),
        ("integer", "Integer"),
        ("boolean", "Boolean"),
        ("json", "JSON"),
    ]

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    value_type = models.CharField(max_length=20, choices=VALUE_TYPE_CHOICES, default="string")
    description = models.TextField(blank=True, help_text="Explain what this setting does")

    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value[:50]}{'...' if len(self.value) > 50 else ''}"

    @classmethod
    def get_value(cls, key: str, default: Any = None) -> Any:
        """Get configuration value with type casting."""
        try:
            config = cls.objects.get(key=key)
            if config.value_type == "integer":
                return int(config.value)
            elif config.value_type == "boolean":
                return config.value.lower() in ("true", "1", "yes")
            elif config.value_type == "json":
                return json.loads(config.value)
            return config.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_value(
        cls, key: str, value: Any, value_type: str = "string", description: str = ""
    ) -> "SystemConfiguration":
        """Set configuration value."""
        if value_type == "json" and not isinstance(value, str):
            value = json.dumps(value)
        elif value_type == "boolean":
            value = "true" if value else "false"
        else:
            value = str(value)

        config, _ = cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "value_type": value_type, "description": description},
        )
        return config


class QueryAuditLog(models.Model):
    """Audit log for database queries."""

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    database = models.ForeignKey(DatabaseConnection, on_delete=models.SET_NULL, null=True)
    query = models.TextField()
    row_count = models.IntegerField(null=True)
    execution_time_ms = models.IntegerField(null=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Query Audit Log"
        verbose_name_plural = "Query Audit Logs"

    def __str__(self) -> str:
        return f"{self.user} - {self.database} - {self.created_at}"
