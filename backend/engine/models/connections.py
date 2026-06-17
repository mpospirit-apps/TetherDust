"""Database, documentation source, MCP server, tool, prompt, system config, and query audit models."""  # noqa: E501

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import (
    generate_cb_id,
    generate_cfg_id,
    generate_db_id,
    generate_doc_id,
    generate_mcp_id,
    generate_prm_id,
    generate_qal_id,
    generate_tool_id,
)
from ..integrations.github_client import parse_owner_repo as parse_owner_repo
from .fields import EncryptedCharField, EncryptedJSONField


class DatabaseConnection(models.Model):
    """Client-configurable database connection."""

    class Meta:
        verbose_name = "database connection"
        verbose_name_plural = "database connections"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="idx_dbconn_active_name"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    ENGINE_CHOICES: ClassVar[list[tuple[str, str]]] = [
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

    DEFAULT_PORTS: ClassVar[dict[str, int]] = {
        "postgresql": 5432,
        "mysql": 3306,
        "mssql": 1433,
        "oracle": 1521,
        "mariadb": 3306,
        "clickhouse": 8123,
    }

    __prefix__: ClassVar[str] = "db"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_db_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)

    # Domain
    name = models.CharField(max_length=100, help_text="Unique identifier for this connection")
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
    password = EncryptedCharField(max_length=500, blank=True, db_column="password")
    connection_string = models.TextField(
        verbose_name="connection string",
        blank=True,
        help_text="Optional: Full SQLAlchemy URL (overrides above fields)",
    )
    extra_options = models.JSONField(
        verbose_name="extra options",
        default=dict,
        blank=True,
        help_text="Additional SQLAlchemy connect_args (e.g., SSL settings)",
    )
    read_only = models.BooleanField(
        verbose_name="read only",
        default=True,
        help_text=(
            "Strongly recommended. Runs every query in a read-only database session on "
            "PostgreSQL, MySQL/MariaDB, SQLite, Oracle, and ClickHouse. SQL Server, "
            "BigQuery, and Snowflake cannot enforce this at the session level — use a "
            "read-only database user / IAM role there. All engines are additionally "
            "checked by the SQL validator."
        ),
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.engine})"


class Codebase(models.Model):
    """Client-configurable source-code repository the agent reads on demand.

    A codebase is a first-class "source" alongside databases and documentation:
    the agent browses and reads its files via the codebase MCP tools, and roles
    grant access through ``Role.allowed_codebases``. v1 supports GitHub via the
    REST API (no clone); contents are fetched live and the file tree is cached
    on sync.
    """

    class Meta:
        verbose_name = "codebase"
        verbose_name_plural = "codebases"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    PROVIDER_CHOICES: ClassVar[list[tuple[str, str]]] = [("github", "GitHub")]

    SYNC_PENDING: ClassVar[str] = "pending"
    SYNC_SYNCING: ClassVar[str] = "syncing"
    SYNC_OK: ClassVar[str] = "ok"
    SYNC_ERROR: ClassVar[str] = "error"
    SYNC_STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (SYNC_PENDING, "Pending"),
        (SYNC_SYNCING, "Syncing"),
        (SYNC_OK, "Synced"),
        (SYNC_ERROR, "Error"),
    ]

    # Sensible defaults so the agent isn't flooded with build output / binaries.
    DEFAULT_EXCLUDE_GLOBS: ClassVar[list[str]] = [
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

    __prefix__: ClassVar[str] = "cb"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_cb_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(verbose_name="last synced at", null=True, blank=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)
    sync_status = models.CharField(
        verbose_name="sync status",
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_PENDING,
    )
    sync_error = models.TextField(verbose_name="sync error", blank=True)

    # Domain
    name = models.CharField(max_length=100, help_text="Unique identifier for this codebase")
    description = models.TextField(
        blank=True, help_text="Helps the AI agent understand what this repository contains"
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="github")
    repo_url = models.CharField(
        verbose_name="repo URL",
        max_length=500,
        help_text="e.g. https://github.com/owner/repo",
    )
    branch = models.CharField(
        max_length=255, blank=True, help_text="Leave blank to use the repository's default branch"
    )
    subpath = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional sub-directory to scope to, for monorepos (e.g. services/api)",
    )
    include_globs = models.JSONField(
        verbose_name="include globs",
        default=list,
        blank=True,
        help_text='Glob patterns to include, e.g. ["src/**", "*.py"]. Empty = everything (minus excludes).',  # noqa: E501
    )
    exclude_globs = models.JSONField(
        verbose_name="exclude globs",
        default=list,
        blank=True,
        help_text="Glob patterns to exclude. Empty = a sensible default set (node_modules, build output, binaries).",  # noqa: E501
    )
    access_token = EncryptedCharField(
        verbose_name="access token",
        max_length=500,
        blank=True,
        db_column="access_token",
        help_text="Encrypted GitHub token. Leave blank for public repositories.",
    )
    default_branch = models.CharField(
        verbose_name="default branch", max_length=255, blank=True, help_text="Resolved on sync"
    )
    cached_tree = models.JSONField(
        verbose_name="cached tree",
        default=list,
        blank=True,
        help_text="Cached repository file tree (list of {path, type, size}), refreshed on sync.",
    )

    def __str__(self) -> str:
        return self.name


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
    Sources are auto-discovered via ``DocSourceService.sync_from_filesystem()``
    and assigned to roles for visibility control.
    """

    class Meta:
        verbose_name = "documentation source"
        verbose_name_plural = "documentation sources"
        ordering = ["folder_name"]
        indexes = [
            models.Index(fields=["is_active", "folder_name"], name="idx_docsrc_active_folder"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["folder_name"], name="uq_%(class)s_folder"),
        ]

    class DocType(models.TextChoices):
        DATABASE = "database", "Database"
        CODEBASE = "codebase", "Codebase"
        MANUAL = "manual", "Manual"
        POLICY = "policy", "Policy"
        API = "api", "API"
        REPORT = "report", "Report"
        ONTOLOGY = "ontology", "Ontology"
        RUNBOOK = "runbook", "Runbook"

    __prefix__: ClassVar[str] = "doc"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_doc_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)

    # Domain
    folder_name = models.CharField(
        verbose_name="folder name",
        max_length=255,
        help_text="Folder name inside the documentations/ directory",
    )
    doc_type = models.CharField(
        verbose_name="type",
        max_length=20,
        choices=DocType.choices,
        default=DocType.DATABASE,
        help_text="The category of documentation this source contains",
    )
    description = models.TextField(
        blank=True, help_text="Helps AI understand what this source contains"
    )
    file_patterns = models.JSONField(
        verbose_name="file patterns",
        default=list,
        blank=True,
        help_text='Glob patterns for files, e.g. ["*.md"] or ["*.py", "*.sql"]. Leave empty for default (*.md).',  # noqa: E501
    )

    def __str__(self) -> str:
        return self.folder_name


class MCPServerConfiguration(models.Model):
    """Admin-configurable MCP server grouping for tools."""

    class Meta:
        verbose_name = "MCP server"
        verbose_name_plural = "MCP servers"
        ordering = ["-is_builtin", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    TRANSPORT_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("", "Local (built-in)"),
        ("sse", "SSE"),
        ("streamable-http", "Streamable HTTP"),
    ]

    __prefix__: ClassVar[str] = "mcp"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_mcp_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)
    is_builtin = models.BooleanField(
        verbose_name="is builtin",
        default=False,
        help_text="Built-in servers cannot be edited or deleted",
    )

    # Domain
    name = models.CharField(max_length=100, help_text="Display name for this MCP server")
    description = models.TextField(blank=True, help_text="What this MCP server provides")
    url = models.CharField(
        verbose_name="URL",
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
    auth_token = EncryptedCharField(
        verbose_name="auth token",
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
    command_env = EncryptedJSONField(
        verbose_name="command env",
        default=dict,
        blank=True,
        db_column="command_env",
        help_text="Encrypted JSON dict of environment variables passed to the subprocess.",
    )

    def __str__(self) -> str:
        return self.name


class ToolConfiguration(models.Model):
    """Admin-configurable MCP tool settings."""

    class Meta:
        verbose_name = "tool configuration"
        verbose_name_plural = "tool configurations"
        ordering = ["category", "display_name"]
        constraints = [
            models.UniqueConstraint(fields=["tool_name"], name="uq_%(class)s_tool_name"),
        ]

    # Feature-based grouping for the built-in tools. Custom-server tools are
    # left uncategorized ("" → shown as "Other").
    CATEGORY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("querying", "Querying"),
        ("docs", "Docs"),
        ("charts", "Charts"),
        ("codebases", "Codebases"),
        ("tethers", "Tethers"),
        ("reports", "Reports"),
    ]

    __prefix__: ClassVar[str] = "tool"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_tool_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_enabled = models.BooleanField(verbose_name="is enabled", default=True)

    # Domain
    tool_name = models.CharField(
        verbose_name="tool name",
        max_length=100,
        help_text="Internal tool name (e.g., 'search_docs')",
    )
    display_name = models.CharField(
        verbose_name="display name", max_length=100, help_text="Human-readable name"
    )
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
    input_schema = models.JSONField(
        verbose_name="input schema",
        default=dict,
        blank=True,
        help_text='MCP tool input schema (JSON Schema). Example: {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}',  # noqa: E501
    )
    source_code = models.TextField(
        verbose_name="source code",
        blank=True,
        default="",
        help_text="Python handler code. Must define an async function handle(arguments: dict) -> str that returns the tool result text.",  # noqa: E501
    )
    settings = models.JSONField(
        default=dict, blank=True, help_text="Tool-specific settings (e.g., max_results, timeout)"
    )

    # Relations
    mcp_server = models.ForeignKey(
        MCPServerConfiguration,
        on_delete=models.CASCADE,
        related_name="tools",
        help_text="MCP server this tool belongs to",
    )

    def __str__(self) -> str:
        return self.display_name


class PromptConfiguration(models.Model):
    """Admin-configurable MCP prompt template."""

    class Meta:
        verbose_name = "prompt configuration"
        verbose_name_plural = "prompt configurations"
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(fields=["prompt_name"], name="uq_%(class)s_prompt_name"),
        ]

    __prefix__: ClassVar[str] = "prm"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_prm_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_enabled = models.BooleanField(verbose_name="is enabled", default=True)

    # Domain
    prompt_name = models.CharField(
        verbose_name="prompt name",
        max_length=100,
        help_text="Internal prompt name (e.g., 'analyze_table')",
    )
    display_name = models.CharField(
        verbose_name="display name",
        max_length=100,
        help_text="Human-readable name shown in autocomplete",
    )
    content = models.TextField(
        default="",
        help_text="The prompt instructions. This text is prepended to the user's message as context for the AI agent.",  # noqa: E501
    )

    # Relations
    mcp_server = models.ForeignKey(
        MCPServerConfiguration,
        on_delete=models.CASCADE,
        related_name="prompts",
        help_text="MCP server this prompt belongs to",
    )

    def __str__(self) -> str:
        return self.display_name


class SystemConfiguration(models.Model):
    """Key-value store for admin-configurable settings."""

    class Meta:
        verbose_name = "system configuration"
        verbose_name_plural = "system configuration"
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(fields=["key"], name="uq_%(class)s_key"),
        ]

    VALUE_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("string", "String"),
        ("integer", "Integer"),
        ("boolean", "Boolean"),
        ("json", "JSON"),
    ]

    __prefix__: ClassVar[str] = "cfg"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_cfg_id, editable=False)

    # Domain
    key = models.CharField(max_length=100)
    value = models.TextField()
    value_type = models.CharField(
        verbose_name="value type", max_length=20, choices=VALUE_TYPE_CHOICES, default="string"
    )
    description = models.TextField(blank=True, help_text="Explain what this setting does")

    def __str__(self) -> str:
        return f"{self.key} = {self.value[:50]}{'...' if len(self.value) > 50 else ''}"


class QueryAuditLog(models.Model):
    """Audit log for database queries."""

    class Meta:
        verbose_name = "query audit log"
        verbose_name_plural = "query audit logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"], name="idx_qal_recent"),
            models.Index(fields=["success", "-created_at"], name="idx_qal_success_recent"),
            models.Index(fields=["database", "-created_at"], name="idx_qal_db_recent"),
        ]

    __prefix__: ClassVar[str] = "qal"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_qal_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)

    # State
    success = models.BooleanField(default=True)

    # Domain
    query = models.TextField()
    row_count = models.IntegerField(verbose_name="row count", null=True)
    execution_time_ms = models.IntegerField(verbose_name="execution time ms", null=True)
    error_message = models.TextField(verbose_name="error message", blank=True)

    # Relations
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    database = models.ForeignKey(DatabaseConnection, on_delete=models.SET_NULL, null=True)

    def __str__(self) -> str:
        return f"{self.user} - {self.database} - {self.created_at}"
