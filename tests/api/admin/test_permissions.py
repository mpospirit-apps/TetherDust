"""The admin console is staff-only: every endpoint 403s for non-staff/anonymous."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db

# Representative GET-able admin endpoints across the router viewsets + APIViews.
# ``users/`` is excluded — it uses the stricter CanManageUsers permission and is
# covered separately below.
ADMIN_ENDPOINTS = [
    "roles/",
    "databases/",
    "codebases/",
    "agents/",
    "dashboards/",
    "reports/",
    "tethers/",
    "mcp-servers/",
    "settings/general/",
    "audit/",
]


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_non_staff_forbidden(auth_client: Any, endpoint: str) -> None:
    assert auth_client().get(f"/api/v1/admin/{endpoint}").status_code == 403


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_anonymous_forbidden(api_client: Any, endpoint: str) -> None:
    assert api_client.get(f"/api/v1/admin/{endpoint}").status_code == 403


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_staff_allowed(staff_client: Any, endpoint: str) -> None:
    assert staff_client.get(f"/api/v1/admin/{endpoint}").status_code == 200


# ``users/`` needs CanManageUsers (superuser, or staff whose role grants it),
# not just staff.


def test_users_forbidden_for_plain_staff(auth_client: Any) -> None:
    assert auth_client(is_staff=True).get("/api/v1/admin/users/").status_code == 403


def test_users_allowed_for_superuser(auth_client: Any) -> None:
    client = auth_client(is_staff=True, is_superuser=True)
    assert client.get("/api/v1/admin/users/").status_code == 200
