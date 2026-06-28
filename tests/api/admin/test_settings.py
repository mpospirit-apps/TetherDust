"""Admin settings: general key/value config and SMTP (password write-only)."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db


def test_general_get(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/admin/settings/general/")
    assert resp.status_code == 200
    assert "mcp_base_url" in resp.json()


def test_general_put_persists(staff_client: Any) -> None:
    resp = staff_client.put(
        "/api/v1/admin/settings/general/", {"max_row_limit": 500}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["max_row_limit"] == 500


def test_smtp_get_reports_password_presence_only(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/admin/settings/smtp/")
    assert resp.status_code == 200
    assert resp.json()["has_password"] is False


def test_smtp_put_stores_password_write_only(staff_client: Any) -> None:
    resp = staff_client.put(
        "/api/v1/admin/settings/smtp/",
        {"smtp_host": "smtp.example.com", "smtp_password": "secret"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_password"] is True
    assert "smtp_password" not in body  # never echoed back
