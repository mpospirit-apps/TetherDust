"""Fernet-encrypted model fields and the encrypt/decrypt helpers.

The conftest sets a real ``TETHERDUST_ENCRYPTION_KEY``, so these exercise actual
encryption: values are ciphertext at rest, plaintext through the ORM, and legacy
plaintext rows still decode. The missing-key behaviour (fail closed in prod,
warn-and-fallback in DEBUG) is checked by overriding settings.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from engine.models import DatabaseConnection, decrypt_value, encrypt_value

# --- helpers -----------------------------------------------------------------


def _raw_column(model: type, pk: str, column: str) -> str | None:
    """Read a column straight from the DB, bypassing the field's decryption."""
    with connection.cursor() as cur:
        cur.execute(
            f"SELECT {column} FROM {model._meta.db_table} WHERE id = %s",  # noqa: S608
            [pk],
        )
        row = cur.fetchone()
    return row[0] if row else None


# --- encrypt/decrypt helpers -------------------------------------------------


def test_encrypt_changes_value_and_round_trips() -> None:
    token = encrypt_value("s3cret")
    assert token != "s3cret"
    assert decrypt_value(token) == "s3cret"


def test_decrypt_tolerates_plaintext() -> None:
    # A legacy/never-encrypted value decodes to itself rather than blowing up.
    assert decrypt_value("not-a-fernet-token") == "not-a-fernet-token"


def test_empty_values_pass_through() -> None:
    assert encrypt_value("") == ""
    assert decrypt_value("") == ""


# --- encrypted model fields --------------------------------------------------


@pytest.mark.django_db
def test_field_round_trips_through_orm() -> None:
    conn = DatabaseConnection.objects.create(name="enc", engine="postgresql", password="hunter2")
    assert DatabaseConnection.objects.get(pk=conn.pk).password == "hunter2"


@pytest.mark.django_db
def test_field_is_ciphertext_at_rest() -> None:
    conn = DatabaseConnection.objects.create(name="enc", engine="postgresql", password="hunter2")
    raw = _raw_column(DatabaseConnection, conn.pk, "password")
    assert raw is not None and raw != "hunter2"
    assert decrypt_value(raw) == "hunter2"


@pytest.mark.django_db
def test_field_tolerates_legacy_plaintext_row() -> None:
    conn = DatabaseConnection.objects.create(name="enc", engine="postgresql", password="x")
    with connection.cursor() as cur:
        cur.execute(
            f"UPDATE {DatabaseConnection._meta.db_table} SET password = %s WHERE id = %s",  # noqa: S608
            ["legacy-plain", conn.pk],
        )
    assert DatabaseConnection.objects.get(pk=conn.pk).password == "legacy-plain"


@pytest.mark.django_db
def test_blank_encrypted_field_stays_blank() -> None:
    conn = DatabaseConnection.objects.create(name="enc", engine="postgresql", password="")
    assert DatabaseConnection.objects.get(pk=conn.pk).password == ""
    assert _raw_column(DatabaseConnection, conn.pk, "password") == ""


@pytest.mark.django_db
def test_encrypted_json_field_round_trips() -> None:
    # ``MCPServerConfiguration.command_env`` is an EncryptedJSONField.
    from engine.models import MCPServerConfiguration

    server = MCPServerConfiguration.objects.create(name="local", command_env={"API_KEY": "v"})
    reloaded = MCPServerConfiguration.objects.get(pk=server.pk)
    assert reloaded.command_env == {"API_KEY": "v"}
    raw = _raw_column(MCPServerConfiguration, server.pk, "command_env")
    assert raw and "API_KEY" not in raw  # stored encrypted, not as readable JSON


# --- missing-key behaviour ---------------------------------------------------


def test_encrypt_fails_closed_without_key_in_production(settings: Any) -> None:
    settings.TETHERDUST_ENCRYPTION_KEY = ""
    settings.DEBUG = False
    with pytest.raises(ImproperlyConfigured):
        encrypt_value("secret")


def test_encrypt_falls_back_to_plaintext_in_debug(settings: Any) -> None:
    settings.TETHERDUST_ENCRYPTION_KEY = ""
    settings.DEBUG = True
    assert encrypt_value("secret") == "secret"  # warns once, does not raise
