"""Unified query execution across SQL backends.

ClickHouse uses `clickhouse-connect` (HTTP) which does not ship a SQLAlchemy
dialect, so a `clickhouse+connect://...` URL fails plugin lookup. This module
hides the branching: callers pass a `DatabaseConnection` and get back a
backend-agnostic `(columns, rows)` tuple where rows are plain lists.
"""

from typing import Any

from sqlalchemy import create_engine, text


def run_query(db: Any, sql: str) -> tuple[list[str], list[list[Any]]]:
    """Execute `sql` against `db` and return (columns, rows-as-lists)."""
    if db.engine == "clickhouse":
        return _run_clickhouse(db, sql)
    return _run_sqlalchemy(db, sql)


def ping(db: Any, *, timeout: int = 10) -> None:
    """Run `SELECT 1` against `db`. Raises on failure."""
    if db.engine == "clickhouse":
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=db.host,
            port=db.port,
            username=db.username or "default",
            password=db.password or "",
            database=db.database or "default",
            connect_timeout=timeout,
            send_receive_timeout=timeout,
        )
        try:
            client.command("SELECT 1")
        finally:
            client.close()
        return

    # Map each engine to its driver's connect-timeout kwarg so an
    # unreachable-but-resolvable host fails fast instead of hanging at the
    # OS default TCP timeout (which gets the ASGI worker killed by Daphne).
    timeout_kwarg = {
        "postgresql": "connect_timeout",
        "mysql": "connect_timeout",
        "mariadb": "connect_timeout",
        "mssql": "login_timeout",
        "snowflake": "login_timeout",
    }.get(db.engine)

    connect_args = dict(db.extra_options or {})
    if timeout_kwarg and timeout_kwarg not in connect_args:
        connect_args[timeout_kwarg] = timeout

    engine = create_engine(
        db.get_connection_url(),
        connect_args=connect_args,
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def _run_clickhouse(db: Any, sql: str) -> tuple[list[str], list[list[Any]]]:
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=db.host,
        port=db.port,
        username=db.username or "default",
        password=db.password or "",
        database=db.database or "default",
    )
    try:
        result = client.query(sql)
        return list(result.column_names), [list(row) for row in result.result_rows]
    finally:
        client.close()


def _run_sqlalchemy(db: Any, sql: str) -> tuple[list[str], list[list[Any]]]:
    engine = create_engine(
        db.get_connection_url(),
        pool_pre_ping=True,
        connect_args=db.extra_options or {},
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
        return columns, rows
    finally:
        engine.dispose()
