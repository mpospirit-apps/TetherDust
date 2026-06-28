"""Public tethers API — role scoping (incl. the can_view_tethers flag) + graph."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_denied_when_role_flag_off(auth_client: Any, make_role: Any) -> None:
    role = make_role(can_view_tethers=False)
    tether = baker.make("engine.Tether", is_active=True)
    tether.allowed_roles.set([role])
    assert auth_client(role=role).get("/api/v1/tethers/").status_code == 403


def test_staff_sees_all_active(staff_client: Any) -> None:
    baker.make("engine.Tether", is_active=True, name="T1")
    resp = staff_client.get("/api/v1/tethers/")
    assert resp.status_code == 200
    assert any(t["name"] == "T1" for t in resp.json()["tethers"])


def test_role_scoped(auth_client: Any, make_role: Any) -> None:
    role = make_role(can_view_tethers=True)
    mine = baker.make("engine.Tether", is_active=True, name="Mine")
    mine.allowed_roles.set([role])
    other = baker.make("engine.Tether", is_active=True, name="Theirs")
    other.allowed_roles.set([make_role(can_view_tethers=True)])

    resp = auth_client(role=role).get("/api/v1/tethers/")
    assert {t["name"] for t in resp.json()["tethers"]} == {"Mine"}


def test_graph_pending_without_version(staff_client: Any) -> None:
    tether = baker.make("engine.Tether", is_active=True)
    resp = staff_client.get(f"/api/v1/tethers/{tether.id}/graph/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_detail_404_for_missing(staff_client: Any) -> None:
    assert staff_client.get("/api/v1/tethers/tth_missing/").status_code == 404
