"""SystemConfigService — typed key/value store with declared-type coercion."""

from __future__ import annotations

import pytest
from engine.models import SystemConfiguration
from engine.services import SystemConfigService, get

pytestmark = pytest.mark.django_db


@pytest.fixture
def config() -> SystemConfigService:
    return get(SystemConfigService)


def test_missing_key_returns_default(config: SystemConfigService) -> None:
    assert config.get_value("absent", "fallback") == "fallback"
    assert config.get_value("absent") is None


def test_string_round_trip(config: SystemConfigService) -> None:
    config.set_value("name", "tetherdust")
    assert config.get_value("name") == "tetherdust"


def test_integer_coercion(config: SystemConfigService) -> None:
    config.set_value("limit", 250, "integer")
    assert config.get_value("limit") == 250  # int, not "250"


def test_boolean_coercion(config: SystemConfigService) -> None:
    config.set_value("flag", True, "boolean")
    assert config.get_value("flag") is True
    config.set_value("flag", False, "boolean")
    assert config.get_value("flag") is False


def test_json_coercion(config: SystemConfigService) -> None:
    config.set_value("payload", {"a": 1, "b": [2, 3]}, "json")
    assert config.get_value("payload") == {"a": 1, "b": [2, 3]}


def test_set_value_upserts(config: SystemConfigService) -> None:
    config.set_value("key", "v1")
    config.set_value("key", "v2")
    assert config.get_value("key") == "v2"
    assert SystemConfiguration.objects.filter(key="key").count() == 1
