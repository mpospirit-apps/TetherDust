"""AgentService — active-agent invariant, lookup, and credential decoding."""

from __future__ import annotations

import base64
import datetime
import json
from typing import Any

import pytest
from engine.models import AgentConfiguration
from engine.services import AgentService, get
from model_bakery import baker


def _jwt(claims: dict[str, Any]) -> str:
    """A signature-free JWT (header.payload.sig) carrying ``claims`` for display decoding."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"hdr.{payload}.sig"


# --- get_active / save_config (DB) ------------------------------------------


@pytest.mark.django_db
def test_get_active_returns_active_or_none() -> None:
    service = get(AgentService)
    assert service.get_active() is None
    agent = baker.make("engine.AgentConfiguration", is_active=True)
    assert service.get_active() == agent


@pytest.mark.django_db
def test_save_config_enforces_single_active(mocker: Any) -> None:
    # save_config also pushes the prompt to the agent container; stub that out.
    mocker.patch.object(AgentService, "sync_agents_md")
    service = get(AgentService)

    first = baker.make("engine.AgentConfiguration", is_active=True)
    second = baker.make("engine.AgentConfiguration", is_active=False)

    second.is_active = True
    service.save_config(second)

    first.refresh_from_db()
    assert first.is_active is False
    assert AgentConfiguration.objects.filter(is_active=True).count() == 1


# --- get_auth_info (pure: reads the in-memory attribute) --------------------


def test_get_auth_info_decodes_identity_and_expiry() -> None:
    service = get(AgentService)
    auth = {
        "tokens": {
            "id_token": _jwt(
                {
                    "email": "user@example.com",
                    "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
                }
            ),
            "access_token": _jwt({"exp": 1893456000}),  # 2030-01-01 UTC
        }
    }
    agent = AgentConfiguration(auth_token=json.dumps(auth))

    info = service.get_auth_info(agent)
    assert info is not None
    assert info["email"] == "user@example.com"
    assert info["plan"] == "plus"
    assert info["expires_at"] == datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)


def test_get_auth_info_none_without_token() -> None:
    assert get(AgentService).get_auth_info(AgentConfiguration(auth_token="")) is None


def test_get_auth_info_none_for_non_json() -> None:
    assert get(AgentService).get_auth_info(AgentConfiguration(auth_token="not json")) is None
