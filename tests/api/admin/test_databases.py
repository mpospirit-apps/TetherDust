"""Admin database-connection CRUD, engine metadata, and the connectivity test."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_create_hides_write_only_password(staff_client: Any) -> None:
    payload = {
        "name": "analytics",
        "engine": "postgresql",
        "host": "db",
        "database": "app",
        "username": "u",
        "password": "secret",
    }
    resp = staff_client.post("/api/v1/admin/databases/", payload, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("db_")
    assert "password" not in body  # write-only


def test_engines_metadata(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/admin/databases/engines/")
    assert resp.status_code == 200
    assert "choices" in resp.json() and "default_ports" in resp.json()


def test_test_action_uses_ping(staff_client: Any, mocker: Any) -> None:
    db = baker.make("engine.DatabaseConnection", is_active=True)
    mocker.patch("engine.engines.db_runner.ping", return_value=None)  # no real connection
    resp = staff_client.post(f"/api/v1/admin/databases/{db.id}/test/")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
