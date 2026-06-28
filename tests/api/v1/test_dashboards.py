"""Public dashboards API — role scoping, detail, and chart data."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_denied_without_access(auth_client: Any) -> None:
    assert auth_client().get("/api/v1/dashboards/").status_code == 403


def test_staff_sees_all_active(staff_client: Any) -> None:
    baker.make("engine.Dashboard", is_active=True, name="D1")
    resp = staff_client.get("/api/v1/dashboards/")
    assert resp.status_code == 200
    assert any(d["name"] == "D1" for d in resp.json()["dashboards"])


def test_role_scoped(auth_client: Any, make_role: Any) -> None:
    role = make_role()
    mine = baker.make("engine.Dashboard", is_active=True, name="Mine")
    mine.allowed_roles.set([role])
    baker.make("engine.Dashboard", is_active=True, name="Theirs").allowed_roles.set([make_role()])

    resp = auth_client(role=role).get("/api/v1/dashboards/")
    assert {d["name"] for d in resp.json()["dashboards"]} == {"Mine"}


def test_detail_404_when_not_visible(auth_client: Any, make_role: Any) -> None:
    role = make_role()
    # Grant one dashboard so CanViewDashboards passes, then request a different one.
    baker.make("engine.Dashboard", is_active=True).allowed_roles.set([role])
    hidden = baker.make("engine.Dashboard", is_active=True)
    hidden.allowed_roles.set([make_role()])

    resp = auth_client(role=role).get(f"/api/v1/dashboards/{hidden.id}/")
    assert resp.status_code == 404


def test_chart_data_staff(staff_client: Any, mocker: Any) -> None:
    chart = baker.make("engine.Chart")
    mocker.patch(
        "api.v1.dashboards.chart_data",
        return_value={"columns": ["n"], "data": [], "cached": False, "refreshed_at": None},
    )
    resp = staff_client.get(f"/api/v1/charts/{chart.id}/data/")
    assert resp.status_code == 200
    assert resp.json()["columns"] == ["n"]


def test_chart_data_missing_404(staff_client: Any) -> None:
    assert staff_client.get("/api/v1/charts/cht_missing/data/").status_code == 404
