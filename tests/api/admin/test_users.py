"""Admin user API: superuser protection, self-lockout guards, password rules,
role assignment on superusers, and staying signed in after your own password
change."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client

pytestmark = pytest.mark.django_db

URL = "/api/v1/admin/users/"
STRONG = "Plum-orbit-7741"


@pytest.fixture
def manager(make_user: Any, make_role: Any) -> User:
    """A non-superuser allowed to manage users (active admin role + the flag)."""
    role = make_role(is_admin_role=True, can_manage_users=True)
    return make_user(role=role, is_staff=True)


def test_create_with_role_makes_admin_staff(
    auth_client: Any, manager: User, make_role: Any
) -> None:
    role = make_role(is_admin_role=True)
    resp = auth_client(user=manager).post(
        URL, {"username": "ana", "password": STRONG, "role": role.id}, format="json"
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_staff"] is True
    assert body["role_name"] == role.name
    assert body["role_is_active"] is True
    assert User.objects.get(username="ana").check_password(STRONG)


# --- passwords ---------------------------------------------------------------


def test_create_needs_a_password(auth_client: Any, manager: User) -> None:
    resp = auth_client(user=manager).post(URL, {"username": "nopw"}, format="json")
    assert resp.status_code == 400
    assert "password" in resp.json()
    assert not User.objects.filter(username="nopw").exists()


@pytest.mark.parametrize("password", ["1", "password", "12345678901"])
def test_weak_passwords_rejected(auth_client: Any, manager: User, password: str) -> None:
    resp = auth_client(user=manager).post(
        URL, {"username": "weak", "password": password}, format="json"
    )
    assert resp.status_code == 400
    assert "password" in resp.json()


def test_weak_password_rejected_on_update(auth_client: Any, manager: User, make_user: Any) -> None:
    target = make_user()
    resp = auth_client(user=manager).patch(f"{URL}{target.id}/", {"password": "1"}, format="json")
    assert resp.status_code == 400


def test_own_password_change_keeps_session(make_user: Any, make_role: Any) -> None:
    role = make_role(is_admin_role=True, can_manage_users=True)
    user = make_user(role=role, is_staff=True, password=STRONG)
    client = Client()
    assert client.login(username=user.username, password=STRONG)

    resp = client.patch(
        f"{URL}{user.id}/",
        data='{"password": "Quiet-harbor-2290"}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert client.get(URL).status_code == 200


# --- superuser accounts ------------------------------------------------------


def test_manager_cannot_change_superuser(auth_client: Any, manager: User, make_user: Any) -> None:
    su = make_user(is_staff=True, is_superuser=True, password=STRONG)
    client = auth_client(user=manager)
    assert (
        client.patch(f"{URL}{su.id}/", {"password": "Quiet-harbor-2290"}, format="json").status_code
        == 403
    )
    assert client.patch(f"{URL}{su.id}/", {"is_active": False}, format="json").status_code == 403
    assert client.delete(f"{URL}{su.id}/").status_code == 403
    su.refresh_from_db()
    assert su.check_password(STRONG)
    assert su.is_active


def test_superuser_role_change_is_saved(auth_client: Any, make_user: Any, make_role: Any) -> None:
    acting = make_user(is_staff=True, is_superuser=True)
    target = make_user(is_staff=True, is_superuser=True)
    role = make_role()
    resp = auth_client(user=acting).patch(f"{URL}{target.id}/", {"role": role.id}, format="json")
    assert resp.status_code == 200
    assert resp.json()["role_name"] == role.name
    target.refresh_from_db()
    assert target.profile.role_id == role.id
    assert target.is_staff  # a superuser keeps staff whatever the role


# --- self-lockout ------------------------------------------------------------


def test_cannot_deactivate_self(auth_client: Any, manager: User) -> None:
    resp = auth_client(user=manager).patch(
        f"{URL}{manager.id}/", {"is_active": False}, format="json"
    )
    assert resp.status_code == 400
    manager.refresh_from_db()
    assert manager.is_active


@pytest.mark.parametrize(
    "role_kwargs",
    [
        None,  # no role
        {"is_admin_role": False, "can_manage_users": True},
        {"is_admin_role": True, "can_manage_users": False},
        {"is_admin_role": True, "can_manage_users": True, "is_active": False},
    ],
)
def test_cannot_drop_own_user_management(
    auth_client: Any, manager: User, make_role: Any, role_kwargs: dict[str, Any] | None
) -> None:
    role = make_role(**role_kwargs) if role_kwargs is not None else None
    resp = auth_client(user=manager).patch(
        f"{URL}{manager.id}/", {"role": role.id if role else None}, format="json"
    )
    assert resp.status_code == 400
    manager.refresh_from_db()
    assert manager.is_staff


def test_can_move_self_to_another_managing_role(
    auth_client: Any, manager: User, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, can_manage_users=True)
    resp = auth_client(user=manager).patch(f"{URL}{manager.id}/", {"role": role.id}, format="json")
    assert resp.status_code == 200


def test_cannot_delete_self(auth_client: Any, manager: User) -> None:
    assert auth_client(user=manager).delete(f"{URL}{manager.id}/").status_code == 400
