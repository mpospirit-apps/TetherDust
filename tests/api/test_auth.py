"""Session-auth endpoints: csrf, login, logout, me."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db


def test_csrf_sets_cookie(api_client: Any) -> None:
    resp = api_client.get("/api/v1/auth/csrf/")
    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies


def test_login_success_returns_user_payload(api_client: Any, make_user: Any) -> None:
    make_user(username="alice", password="pw")
    resp = api_client.post(
        "/api/v1/auth/login/", {"username": "alice", "password": "pw"}, format="json"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert "permissions" in body


def test_login_bad_credentials(api_client: Any, make_user: Any) -> None:
    make_user(username="bob", password="pw")
    resp = api_client.post(
        "/api/v1/auth/login/", {"username": "bob", "password": "WRONG"}, format="json"
    )
    assert resp.status_code == 401


def test_me_requires_authentication(api_client: Any) -> None:
    assert api_client.get("/api/v1/auth/me/").status_code == 403


def test_me_returns_capability_flags(auth_client: Any, make_user: Any) -> None:
    user = make_user(is_staff=True, username="carol")
    resp = auth_client(user=user).get("/api/v1/auth/me/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "carol"
    assert body["is_staff"] is True
    assert set(body["permissions"]) >= {"can_chat", "can_view_reports", "can_view_dashboards"}


def test_logout(api_client: Any, make_user: Any) -> None:
    make_user(username="dave", password="pw")
    api_client.post("/api/v1/auth/login/", {"username": "dave", "password": "pw"}, format="json")
    assert api_client.post("/api/v1/auth/logout/").status_code == 204
