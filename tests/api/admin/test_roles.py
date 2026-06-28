"""Admin role CRUD, the grants option-list, and the in-use delete guard."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db


def test_create(staff_client: Any) -> None:
    resp = staff_client.post("/api/v1/admin/roles/", {"name": "Analyst"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["id"].startswith("rol_")


def test_create_requires_name(staff_client: Any) -> None:
    assert staff_client.post("/api/v1/admin/roles/", {}, format="json").status_code == 400


def test_update(staff_client: Any, make_role: Any) -> None:
    role = make_role(name="Old")
    resp = staff_client.patch(f"/api/v1/admin/roles/{role.id}/", {"name": "New"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_delete(staff_client: Any, make_role: Any) -> None:
    role = make_role()
    assert staff_client.delete(f"/api/v1/admin/roles/{role.id}/").status_code == 204


def test_delete_in_use_returns_400(staff_client: Any, make_user: Any, make_role: Any) -> None:
    role = make_role()
    make_user(role=role)  # role is PROTECTed by the profile FK
    resp = staff_client.delete(f"/api/v1/admin/roles/{role.id}/")
    assert resp.status_code == 400
    assert "Cannot delete" in resp.json()["detail"]


def test_grants_option_lists(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/admin/roles/grants/")
    assert resp.status_code == 200
    assert set(resp.json()) >= {"tools", "databases", "doc_sources", "codebases", "mcp_servers"}
