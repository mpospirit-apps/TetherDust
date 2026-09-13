"""Admin role CRUD, the grants option-list, the in-use delete guard, who may
change a role, the row-limit floor, and the role → staff sync."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_client(auth_client: Any) -> Any:
    """A client allowed to change roles (superuser; see ``CanManageUsers``)."""
    return auth_client(is_staff=True, is_superuser=True)


def test_create(manager_client: Any) -> None:
    resp = manager_client.post("/api/v1/admin/roles/", {"name": "Analyst"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["id"].startswith("rol_")


def test_create_requires_name(manager_client: Any) -> None:
    assert manager_client.post("/api/v1/admin/roles/", {}, format="json").status_code == 400


def test_update(manager_client: Any, make_role: Any) -> None:
    role = make_role(name="Old")
    resp = manager_client.patch(f"/api/v1/admin/roles/{role.id}/", {"name": "New"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_delete(manager_client: Any, make_role: Any) -> None:
    role = make_role()
    assert manager_client.delete(f"/api/v1/admin/roles/{role.id}/").status_code == 204


def test_delete_in_use_returns_400(manager_client: Any, make_user: Any, make_role: Any) -> None:
    role = make_role()
    make_user(role=role)  # role is PROTECTed by the profile FK
    resp = manager_client.delete(f"/api/v1/admin/roles/{role.id}/")
    assert resp.status_code == 400
    assert "Cannot delete" in resp.json()["detail"]


def test_grants_option_lists(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/admin/roles/grants/")
    assert resp.status_code == 200
    assert set(resp.json()) >= {"tools", "databases", "doc_sources", "codebases", "mcp_servers"}


# --- who may change a role ---------------------------------------------------
# Reading is open to all staff (the dashboard/report/tether forms pick roles);
# writing is user management, gated like the user admin API.


def test_plain_staff_can_read(staff_client: Any, make_role: Any) -> None:
    role = make_role()
    assert staff_client.get("/api/v1/admin/roles/").status_code == 200
    assert staff_client.get(f"/api/v1/admin/roles/{role.id}/").status_code == 200
    assert staff_client.get("/api/v1/admin/roles/grants/").status_code == 200


def test_plain_staff_cannot_write(staff_client: Any, make_role: Any) -> None:
    role = make_role()
    url = f"/api/v1/admin/roles/{role.id}/"
    assert (
        staff_client.post("/api/v1/admin/roles/", {"name": "X"}, format="json").status_code == 403
    )
    assert staff_client.patch(url, {"name": "Y"}, format="json").status_code == 403
    assert staff_client.delete(url).status_code == 403


def test_staff_cannot_grant_themselves_user_management(
    auth_client: Any, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, can_manage_users=False)
    client = auth_client(user=make_user(role=role, is_staff=True))
    resp = client.patch(
        f"/api/v1/admin/roles/{role.id}/", {"can_manage_users": True}, format="json"
    )
    assert resp.status_code == 403
    assert client.get("/api/v1/admin/users/").status_code == 403


def test_staff_with_manage_users_role_can_write(
    auth_client: Any, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, can_manage_users=True)
    client = auth_client(user=make_user(role=role, is_staff=True))
    assert client.post("/api/v1/admin/roles/", {"name": "Z"}, format="json").status_code == 201


def test_inactive_manage_users_role_cannot_write(
    auth_client: Any, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, can_manage_users=True, is_active=False)
    client = auth_client(user=make_user(role=role, is_staff=True))
    assert client.post("/api/v1/admin/roles/", {"name": "Z"}, format="json").status_code == 403


# --- row limit -----------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, -5, None])
def test_row_limit_must_be_at_least_one(manager_client: Any, limit: int | None) -> None:
    resp = manager_client.post(
        "/api/v1/admin/roles/", {"name": "Capped", "max_row_limit": limit}, format="json"
    )
    assert resp.status_code == 400
    assert "max_row_limit" in resp.json()


def test_row_limit_of_one_is_accepted(manager_client: Any) -> None:
    resp = manager_client.post(
        "/api/v1/admin/roles/", {"name": "One", "max_row_limit": 1}, format="json"
    )
    assert resp.status_code == 201


# --- role → staff sync -----------------------------------------------------------


def test_deactivating_admin_role_demotes_its_users(
    manager_client: Any, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True)
    user = make_user(role=role, is_staff=True)
    resp = manager_client.patch(
        f"/api/v1/admin/roles/{role.id}/", {"is_active": False}, format="json"
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.is_staff is False

    manager_client.patch(f"/api/v1/admin/roles/{role.id}/", {"is_active": True}, format="json")
    user.refresh_from_db()
    assert user.is_staff is True


def test_assigning_inactive_admin_role_grants_no_staff(
    manager_client: Any, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, is_active=False)
    user = make_user()
    resp = manager_client.patch(f"/api/v1/admin/users/{user.pk}/", {"role": role.id}, format="json")
    assert resp.status_code == 200
    assert resp.json()["is_staff"] is False
