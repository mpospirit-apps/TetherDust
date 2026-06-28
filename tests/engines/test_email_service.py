"""email_service: SMTP config assembly and send guards (no real mail sent)."""

from __future__ import annotations

import pytest
from engine.engines import email_service
from engine.models import encrypt_value
from engine.services import SystemConfigService, get

pytestmark = pytest.mark.django_db


def _set(key: str, value: object, value_type: str = "string") -> None:
    get(SystemConfigService).set_value(key, value, value_type)


def test_is_smtp_configured_reflects_host() -> None:
    assert email_service.is_smtp_configured() is False
    _set("smtp_host", "smtp.example.com")
    assert email_service.is_smtp_configured() is True


def test_get_smtp_config_none_without_host() -> None:
    assert email_service.get_smtp_config() is None


def test_get_smtp_config_assembles_and_decrypts() -> None:
    _set("smtp_host", "smtp.example.com")
    _set("smtp_port", 2525, "integer")
    _set("smtp_username", "mailer")
    _set("smtp_password", encrypt_value("s3cret"))  # stored encrypted
    _set("smtp_from_email", "reports@example.com")

    config = email_service.get_smtp_config()
    assert config is not None
    assert config["host"] == "smtp.example.com"
    assert config["port"] == 2525  # integer-coerced
    assert config["password"] == "s3cret"  # decrypted back to plaintext
    assert config["from_email"] == "reports@example.com"


def test_get_email_connection_none_when_unconfigured() -> None:
    assert email_service.get_email_connection() is None


def test_get_email_connection_built_from_config() -> None:
    _set("smtp_host", "smtp.example.com")
    connection = email_service.get_email_connection()
    assert connection is not None  # backend constructed, not yet opened


def test_send_report_email_false_when_not_configured() -> None:
    assert email_service.send_report_email("rex_x", ["a@example.com"]) is False


def test_send_report_email_false_without_recipients() -> None:
    _set("smtp_host", "smtp.example.com")
    assert email_service.send_report_email("rex_x", []) is False
