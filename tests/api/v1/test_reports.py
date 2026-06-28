"""Public reports API — role scoping + latest lookup."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_denied_without_access(auth_client: Any) -> None:
    # A user with no role cannot view reports → CanViewReports denies.
    assert auth_client().get("/api/v1/reports/").status_code == 403


def test_staff_sees_all_active(staff_client: Any) -> None:
    baker.make("engine.ReportDefinition", is_active=True, name="R1")
    baker.make("engine.ReportDefinition", is_active=False, name="R2")
    resp = staff_client.get("/api/v1/reports/")
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()["reports"]}
    assert "R1" in names and "R2" not in names


def test_role_scoped(auth_client: Any, make_role: Any) -> None:
    role = make_role()
    mine = baker.make("engine.ReportDefinition", is_active=True, name="Mine")
    mine.allowed_roles.set([role])
    theirs = baker.make("engine.ReportDefinition", is_active=True, name="Theirs")
    theirs.allowed_roles.set([make_role()])

    resp = auth_client(role=role).get("/api/v1/reports/")
    assert resp.status_code == 200
    assert {r["name"] for r in resp.json()["reports"]} == {"Mine"}


def test_latest_404_for_missing(staff_client: Any) -> None:
    assert staff_client.get("/api/v1/reports/rpt_missing/latest/").status_code == 404


def test_latest_200_with_no_execution(staff_client: Any) -> None:
    report = baker.make("engine.ReportDefinition", is_active=True)
    resp = staff_client.get(f"/api/v1/reports/{report.id}/latest/")
    assert resp.status_code == 200
    assert resp.json()["execution"] is None
