"""SQLAlchemy connection manager for multi-database support.

Handles database configuration, connection pooling, and query execution.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlglot import expressions as exp

logger = logging.getLogger(__name__)


class QueryValidationError(Exception):
    """Raised when a query fails validation."""

    pass


# TetherDust engine name -> sqlglot dialect name. Engines absent here are parsed
# with sqlglot's default dialect, which still rejects writes correctly.
_SQLGLOT_DIALECTS = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "oracle": "oracle",
    "sqlite": "sqlite",
    "clickhouse": "clickhouse",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
}

# Session-scoped statement that puts a connection into read-only mode, by engine.
# Issued once per pooled connection via a connect-time event (see _get_engine), so
# it applies to every transaction on that connection. These statements are
# non-transactional and persist for the connection's life. Oracle has no
# session-level form (handled per-transaction in execute_query). SQL Server,
# BigQuery, and Snowflake have no session read-only at all — they rely on a
# read-only database user / IAM role plus the SQL validator.
_READONLY_SESSION_SQL = {
    "postgresql": "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
    "mysql": "SET SESSION TRANSACTION READ ONLY",
    "mariadb": "SET SESSION TRANSACTION READ ONLY",
    "sqlite": "PRAGMA query_only = ON",
}

# Statement node types that mutate data/schema or run procedural code. Any of
# these anywhere in the parse tree (including inside a CTE) fails validation.
# `exp.Command` catches anything sqlglot can't structure into a known read node
# (EXEC, CALL, SET, VACUUM, GRANT, …), so the check fails closed.
_FORBIDDEN_NODES = tuple(
    t
    for t in (
        getattr(exp, name, None)
        for name in (
            "Insert",
            "Update",
            "Delete",
            "Merge",
            "Drop",
            "Create",
            "Alter",
            "TruncateTable",
            "Command",
            "Set",
            "Grant",
            "Copy",
            # SELECT ... INTO (creates a table; MySQL INTO OUTFILE/DUMPFILE writes files)
            "Into",
        )
    )
    if t is not None
)

# Expression types allowed as the single top-level statement: a SELECT, a set
# operation (UNION/EXCEPT/INTERSECT), or a parenthesized/sub-query wrapping one.
_ALLOWED_ROOTS = tuple(
    t
    for t in (
        getattr(exp, name, None)
        for name in ("Select", "Union", "Except", "Intersect", "SetOperation", "Subquery", "Paren")
    )
    if t is not None
)


def validate_read_only_sql(sql: str, engine: str | None = None) -> None:
    """Validate that ``sql`` is a single read-only statement.

    Uses sqlglot to parse the SQL for the given engine's dialect and rejects
    anything that is not exactly one SELECT/CTE/set-operation, including
    multi-statement input and data-modifying CTEs. Fails closed: unparseable
    SQL is rejected.

    Raises:
        QueryValidationError: If the query is not a safe read-only statement.
    """
    if not sql or not sql.strip():
        raise QueryValidationError("Query cannot be empty.")

    dialect = _SQLGLOT_DIALECTS.get(engine or "")
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    except Exception as err:  # sqlglot.errors.ParseError and friends
        raise QueryValidationError(f"Query could not be parsed as valid SQL: {err}") from err

    if not statements:
        raise QueryValidationError("Query cannot be empty.")
    if len(statements) > 1:
        raise QueryValidationError("Only a single SELECT statement is allowed.")

    root = statements[0]
    if not isinstance(root, _ALLOWED_ROOTS):
        raise QueryValidationError(
            "Only read-only SELECT queries are allowed (the statement must be a "
            "SELECT, CTE, or set operation)."
        )
    if (
        isinstance(root, _FORBIDDEN_NODES)
        or next(root.find_all(*_FORBIDDEN_NODES), None) is not None
    ):
        raise QueryValidationError(
            "Query contains a write or procedural statement. Only read-only "
            "SELECT queries are allowed."
        )


def _decrypt_password(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted password, if encryption key is available."""
    if not encrypted:
        return ""
    key = os.environ.get("TETHERDUST_ENCRYPTION_KEY")
    if not key:
        return encrypted
    try:
        from cryptography.fernet import Fernet, InvalidToken

        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return fernet.decrypt(encrypted.encode()).decode()
    except ImportError:
        logger.debug("cryptography not installed, returning password as-is")
        return encrypted
    except (InvalidToken, Exception):
        # Value may not be encrypted (legacy or invalid)
        return encrypted


@dataclass
class DatabaseConfig:
    """Configuration for a database connection."""

    name: str
    description: str = ""
    engine: str = "sqlite"  # postgresql, mysql, mssql, oracle, sqlite, mariadb, clickhouse
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    connection_string: str = ""  # Optional: override all above fields
    extra_options: dict[str, Any] | None = None
    read_only: bool = True  # Run queries in a read-only session where the engine supports it

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

        port_str = f":{self.port}" if self.port else ""
        # URL-encode password to handle special characters
        from urllib.parse import quote_plus

        password = quote_plus(self.password) if self.password else ""
        auth = f"{self.username}:{password}@" if self.username else ""
        return f"{driver}://{auth}{self.host}{port_str}/{self.database}"


class DatabaseService:
    """Manages database connections and query execution."""

    # Maximum query length in characters (overridable via TETHERDUST_MAX_QUERY_LENGTH)
    MAX_QUERY_LENGTH = int(os.environ.get("TETHERDUST_MAX_QUERY_LENGTH", "10000"))

    # Query execution timeout in seconds (overridable via env)
    DEFAULT_QUERY_TIMEOUT = 30

    def __init__(self) -> None:
        """Initialize database service."""
        self._configs: dict[str, DatabaseConfig] = {}
        self._engines: dict[str, Engine] = {}
        self._loaded = False

        # Query timeout from environment
        try:
            self._query_timeout = int(
                os.getenv("TETHERDUST_QUERY_TIMEOUT", str(self.DEFAULT_QUERY_TIMEOUT))
            )
        except ValueError:
            self._query_timeout = self.DEFAULT_QUERY_TIMEOUT

    def _ensure_loaded(self) -> None:
        """Lazy load configuration if not already loaded."""
        if not self._loaded:
            self._load_config()
            self._loaded = True

    def _load_from_django(self) -> bool:
        """Try to load database configurations from Django DatabaseConnection model.

        Returns True if Django configs were loaded, False if Django is unavailable.
        """
        django_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
        if not django_settings:
            return False

        try:
            import django

            django.setup()
            from core.models import DatabaseConnection

            connections = DatabaseConnection.objects.filter(is_active=True).order_by("name")
            for conn in connections:
                self._configs[conn.name.lower()] = DatabaseConfig(
                    name=conn.name,
                    description=conn.description,
                    engine=conn.engine,
                    host=conn.host,
                    port=conn.port,
                    database=conn.database,
                    username=conn.username,
                    password=conn.password,
                    connection_string=conn.connection_string,
                    extra_options=conn.extra_options or None,
                    read_only=getattr(conn, "read_only", True),
                )
            return True
        except Exception:
            logger.exception("Failed to load database configs from Django")
            return False

    def _load_from_admin_db(self) -> bool:
        """Load database configs by querying Django's admin DB directly via SQLAlchemy.

        This allows the MCP server to read Django-managed DatabaseConnection records
        without needing Django installed. Requires ADMIN_DATABASE_URL env var.

        Returns True if configs were loaded, False otherwise.
        """
        admin_db_url = os.environ.get("ADMIN_DATABASE_URL")
        if not admin_db_url:
            return False

        try:
            admin_engine = create_engine(admin_db_url, pool_pre_ping=True)
            with admin_engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT name, description, engine, host, port, database, "
                        "username, password, connection_string, extra_options, read_only "
                        "FROM core_databaseconnection "
                        "WHERE is_active = true ORDER BY name"
                    )
                )
                rows = result.fetchall()

            admin_engine.dispose()

            if not rows:
                logger.info("No active database connections found in admin DB")
                return False

            for row in rows:
                extra = row[9]  # extra_options (JSON field)
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra) if extra else None
                    except (json.JSONDecodeError, ValueError):
                        extra = None
                elif not extra:
                    extra = None

                self._configs[row[0].lower()] = DatabaseConfig(
                    name=row[0],
                    description=row[1] or "",
                    engine=row[2] or "postgresql",
                    host=row[3] or "",
                    port=row[4],
                    database=row[5] or "",
                    username=row[6] or "",
                    password=_decrypt_password(row[7] or ""),
                    connection_string=row[8] or "",
                    extra_options=extra,
                    read_only=bool(row[10]) if row[10] is not None else True,
                )

            logger.info("Loaded %d database configs from admin DB", len(rows))
            return True
        except Exception:
            logger.exception("Failed to load database configs from admin DB")
            return False

    def _load_config(self) -> None:
        """Load database configuration from Django (preferred) or admin DB."""
        if self._load_from_django():
            return

        if self._load_from_admin_db():
            return

    def _get_engine(self, db_name: str) -> Engine:
        """Get or create SQLAlchemy engine for a database."""
        db_name_lower = db_name.lower()

        if db_name_lower not in self._engines:
            config = self._configs.get(db_name_lower)
            if not config:
                raise ValueError(f"Database '{db_name}' not found in configuration")

            connect_args = config.extra_options or {}
            new_engine = create_engine(
                config.get_connection_url(),
                connect_args=connect_args,
                pool_pre_ping=True,  # Verify connections are alive
                pool_size=int(os.environ.get("TETHERDUST_DB_POOL_SIZE", "5")),
                max_overflow=int(os.environ.get("TETHERDUST_DB_MAX_OVERFLOW", "10")),
            )

            # For engines with a session-level read-only mode, set it once per
            # pooled connection — at connect time, before any transaction begins,
            # which avoids the per-statement transaction-timing pitfalls. The
            # session statements (SET SESSION …, PRAGMA) are non-transactional, so
            # they persist for the life of the connection. Oracle has no session
            # form and is handled per-query in execute_query.
            ro_stmt = _READONLY_SESSION_SQL.get(config.engine) if config.read_only else None
            if ro_stmt is not None:
                _ro_stmt: str = ro_stmt

                @event.listens_for(new_engine, "connect")
                def _set_session_read_only(
                    dbapi_conn: Any, _record: Any, _stmt: str = _ro_stmt
                ) -> None:
                    cursor = dbapi_conn.cursor()
                    try:
                        cursor.execute(_stmt)
                    finally:
                        cursor.close()

            self._engines[db_name_lower] = new_engine

        return self._engines[db_name_lower]

    def _get_ch_client(self, db_name: str) -> Any:
        """Create a clickhouse-connect client for a ClickHouse database."""
        try:
            import clickhouse_connect
        except ImportError:
            raise ImportError(
                "clickhouse-connect is required for ClickHouse. "
                "Install it with: pip install clickhouse-connect"
            )
        config = self._configs[db_name.lower()]
        return clickhouse_connect.get_client(
            host=config.host,
            port=config.port,
            username=config.username or "default",
            password=config.password or "",
            database=config.database or "default",
            connect_timeout=self._query_timeout,
            send_receive_timeout=self._query_timeout,
        )

    def list_databases(self) -> list[DatabaseConfig]:
        """Return all configured databases."""
        self._ensure_loaded()
        return list(self._configs.values())

    def get_database(self, name: str) -> DatabaseConfig | None:
        """Get configuration for a specific database."""
        self._ensure_loaded()
        return self._configs.get(name.lower())

    def validate_query(self, sql: str, engine: str | None = None) -> None:
        """Validate that a query is safe to execute.

        Enforces a length cap, then delegates to the sqlglot-based
        ``validate_read_only_sql`` (parsed for the target engine's dialect).

        Raises:
            QueryValidationError: If the query is not allowed.
        """
        if len(sql or "") > self.MAX_QUERY_LENGTH:
            raise QueryValidationError(
                f"Query exceeds maximum length of {self.MAX_QUERY_LENGTH} characters."
            )

        validate_read_only_sql(sql, engine)

    def execute_query(
        self,
        sql: str,
        database: str | None = None,
        limit: int = 100,
        max_limit: int = 1000,
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute a read-only SQL query.

        Args:
            sql: SQL SELECT query to execute.
            database: Name of the database to query. Uses first configured if None.
            limit: Maximum rows to return (capped by max_limit).
            max_limit: Hard cap on row limit for security.

        Returns:
            Tuple of (list of row dicts, total row count).

        Raises:
            QueryValidationError: If query validation fails.
            ValueError: If database not found.
            SQLAlchemyError: If query execution fails.
        """
        self._ensure_loaded()

        # Resolve the target database first so the query is validated against the
        # correct SQL dialect.
        if database is None:
            if not self._configs:
                raise ValueError("No databases configured")
            database = next(iter(self._configs.keys()))

        config = self._configs[database.lower()]

        # Validate query (parsed for this engine's dialect)
        self.validate_query(sql, engine=config.engine)

        # Apply limit
        effective_limit = min(limit, max_limit)

        # Wrap query with limit if not already present
        sql_upper = sql.upper()
        if "LIMIT" not in sql_upper and "TOP" not in sql_upper:
            if config.engine == "mssql":
                sql = re.sub(
                    r"^(SELECT)\s+",
                    rf"\1 TOP {effective_limit} ",
                    sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
            elif config.engine == "oracle":
                sql = f"{sql} FETCH FIRST {effective_limit} ROWS ONLY"
            else:
                sql = f"{sql} LIMIT {effective_limit}"

        logger.info("Executing query on '%s' (limit=%d)", database, effective_limit)
        logger.debug("SQL: %s", sql[:200])

        if config.engine == "clickhouse":
            client = self._get_ch_client(database)
            try:
                # readonly=1 lets ClickHouse reject any non-read query server-side.
                settings = {"readonly": 1} if config.read_only else None
                result = client.query(sql, settings=settings)
                rows = list(result.named_results())
            finally:
                client.close()
        else:
            engine = self._get_engine(database)
            with engine.connect() as conn:
                conn = conn.execution_options(timeout=self._query_timeout)
                # PG/MySQL/MariaDB/SQLite read-only is set at connect time (see
                # _get_engine). Oracle has no session form, so mark the current
                # transaction read-only as its first statement.
                if config.read_only and config.engine == "oracle":
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                result = conn.execute(text(sql))
                rows = [dict(row._mapping) for row in result.fetchall()]

        row_count = len(rows)
        logger.info("Query returned %d rows", row_count)
        return rows, row_count

    def test_connection(self, database: str) -> tuple[bool, str]:
        """Test connection to a database.

        Returns:
            Tuple of (success, message).
        """
        self._ensure_loaded()

        config = self._configs.get(database.lower())
        try:
            if config and config.engine == "clickhouse":
                client = self._get_ch_client(database)
                client.command("SELECT 1")
                client.close()
            else:
                engine = self._get_engine(database)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            return True, "Connection successful"
        except Exception as e:
            return False, str(e)

    def reload(self) -> None:
        """Force reload of configuration and close all connections."""
        # Close existing engines
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()
        self._configs.clear()
        self._loaded = False
        self._ensure_loaded()
