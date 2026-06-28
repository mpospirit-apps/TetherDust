"""Active-agent status endpoint (API-key branch only — others hit the network)."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_requires_authentication(api_client: Any) -> None:
    assert api_client.get("/api/v1/agent-status/").status_code == 403


def test_no_active_agent(auth_client: Any) -> None:
    resp = auth_client().get("/api/v1/agent-status/")
    assert resp.status_code == 200
    assert resp.json() == {"name": None, "connected": False}


def test_api_key_agent_connected(auth_client: Any) -> None:
    baker.make(
        "engine.AgentConfiguration",
        is_active=True,
        agent_type="openai_platform",
        api_key="sk-x",
        name="GPT",
    )
    assert auth_client().get("/api/v1/agent-status/").json() == {"name": "GPT", "connected": True}


def test_api_key_agent_disconnected_without_key(auth_client: Any) -> None:
    baker.make(
        "engine.AgentConfiguration",
        is_active=True,
        agent_type="openai_platform",
        api_key="",
        name="GPT",
    )
    assert auth_client().get("/api/v1/agent-status/").json() == {"name": "GPT", "connected": False}
