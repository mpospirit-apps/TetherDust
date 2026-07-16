"""ConnectionService / CodebaseService — pure URL & metadata derivation.

These build *unsaved* model instances, so no database is needed — the logic only
reads attributes off the instance.
"""

from __future__ import annotations

from engine.models import Codebase, DatabaseConnection
from engine.services import CodebaseService, ConnectionService, get

# --- ConnectionService.get_connection_url -----------------------------------


def test_postgres_url_with_credentials() -> None:
    conn = DatabaseConnection(
        engine="postgresql", host="db", port=5432, database="app", username="u", password="p@ss"
    )
    url = get(ConnectionService).get_connection_url(conn)
    assert url == "postgresql+psycopg2://u:p%40ss@db:5432/app"


def test_password_is_url_encoded() -> None:
    conn = DatabaseConnection(
        engine="mysql", host="h", port=3306, database="d", username="u", password="a b/c"
    )
    assert "a+b%2Fc@" in get(ConnectionService).get_connection_url(conn)


def test_sqlite_url_ignores_host_and_auth() -> None:
    conn = DatabaseConnection(engine="sqlite", database="/tmp/x.db")
    assert get(ConnectionService).get_connection_url(conn) == "sqlite:////tmp/x.db"


def test_explicit_connection_string_wins() -> None:
    conn = DatabaseConnection(engine="postgresql", connection_string="postgresql://override/db")
    assert get(ConnectionService).get_connection_url(conn) == "postgresql://override/db"


def test_no_port_no_auth() -> None:
    conn = DatabaseConnection(engine="clickhouse", host="h", database="d")
    assert get(ConnectionService).get_connection_url(conn) == "clickhouse+connect://h/d"


def test_unknown_engine_falls_back_to_engine_name() -> None:
    conn = DatabaseConnection(engine="unlisted", host="h", database="d", username="u", password="p")
    assert get(ConnectionService).get_connection_url(conn).startswith("unlisted://u:p@h/d")


# --- CodebaseService --------------------------------------------------------


def test_owner_repo() -> None:
    assert get(CodebaseService).owner_repo(Codebase(repo_url="https://github.com/o/r")) == (
        "o",
        "r",
    )
