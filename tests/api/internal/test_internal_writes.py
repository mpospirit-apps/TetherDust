"""Internal service-token write API (backs the tdmcp mutating tools).

Auth is the ``X-Service-Token`` header only — no session/CSRF. The token matches
``INTERNAL_API_SERVICE_TOKEN`` set in the root conftest. Because
``ServiceTokenAuthentication`` exposes no ``authenticate_header``, both a missing
token (permission) and a wrong token (auth failure) resolve to 403 — they are
told apart by the response body.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from model_bakery import baker

pytestmark = pytest.mark.django_db

# Whatever token the running settings are configured with (.env locally, CI env
# in CI) — the test authenticates with the same value the server expects.
TOKEN = settings.INTERNAL_API_SERVICE_TOKEN


def _post(client: Any, url: str, body: dict[str, Any], token: str | None = TOKEN) -> Any:
    extra = {"HTTP_X_SERVICE_TOKEN": token} if token is not None else {}
    return client.post(url, body, format="json", **extra)


# --- auth --------------------------------------------------------------------


def test_missing_token_is_rejected(api_client: Any) -> None:
    # No token → not authenticated. DRF downgrades 401→403 (no auth header).
    resp = _post(api_client, "/api/internal/dashboards/", {"name": "D"}, token=None)
    assert resp.status_code == 403
    assert "credentials" in resp.json()["detail"].lower()


def test_wrong_token_is_auth_failure(api_client: Any) -> None:
    resp = _post(api_client, "/api/internal/dashboards/", {"name": "D"}, token="bad")
    assert resp.status_code == 403
    assert "Invalid service token" in resp.json()["detail"]


# --- dashboards --------------------------------------------------------------


def test_create_dashboard(api_client: Any) -> None:
    resp = _post(api_client, "/api/internal/dashboards/", {"name": "Sales"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["dashboard_id"].startswith("dsh_")


def test_create_dashboard_requires_name(api_client: Any) -> None:
    assert _post(api_client, "/api/internal/dashboards/", {}).status_code == 400


def test_create_dashboard_rejects_duplicate(api_client: Any) -> None:
    baker.make("engine.Dashboard", name="Dup")
    resp = _post(api_client, "/api/internal/dashboards/", {"name": "Dup"})
    assert resp.status_code == 400


# --- charts ------------------------------------------------------------------


def test_add_chart(api_client: Any) -> None:
    dashboard = baker.make("engine.Dashboard")
    baker.make("engine.DatabaseConnection", is_active=True, name="d1")
    resp = _post(
        api_client,
        f"/api/internal/dashboards/{dashboard.id}/charts/",
        {"title": "Revenue", "database": "d1", "sql_query": "SELECT 1"},
    )
    assert resp.status_code == 201
    assert resp.json()["chart_id"].startswith("cht_")


def test_add_chart_rejects_write_sql(api_client: Any) -> None:
    dashboard = baker.make("engine.Dashboard")
    baker.make("engine.DatabaseConnection", is_active=True, name="d1")
    resp = _post(
        api_client,
        f"/api/internal/dashboards/{dashboard.id}/charts/",
        {"title": "Bad", "database": "d1", "sql_query": "DELETE FROM t"},
    )
    assert resp.status_code == 400


def test_add_chart_missing_dashboard_404(api_client: Any) -> None:
    baker.make("engine.DatabaseConnection", is_active=True, name="d1")
    resp = _post(
        api_client,
        "/api/internal/dashboards/dsh_missing/charts/",
        {"title": "X", "database": "d1", "sql_query": "SELECT 1"},
    )
    assert resp.status_code == 404


def test_update_chart(api_client: Any) -> None:
    chart = baker.make("engine.Chart")
    resp = api_client.patch(
        f"/api/internal/charts/{chart.id}/",
        {"title": "Renamed"},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
    )
    assert resp.status_code == 200
    assert "title" in resp.json()["updated_fields"]


def test_update_chart_nothing_to_update_400(api_client: Any) -> None:
    chart = baker.make("engine.Chart")
    resp = api_client.patch(
        f"/api/internal/charts/{chart.id}/", {}, format="json", HTTP_X_SERVICE_TOKEN=TOKEN
    )
    assert resp.status_code == 400


# --- tether graph ------------------------------------------------------------


def test_save_tether_graph_promotes_version(api_client: Any) -> None:
    version = baker.make("engine.TetherVersion")
    resp = _post(
        api_client,
        f"/api/internal/tether-versions/{version.id}/graph/",
        {"nodes": [], "edges": []},  # an empty graph passes schema validation
    )
    assert resp.status_code == 200
    version.refresh_from_db()
    assert version.status == "success"
    assert version.tether.current_version_id == version.id


def test_save_tether_graph_rejects_invalid_schema(api_client: Any) -> None:
    version = baker.make("engine.TetherVersion")
    resp = _post(
        api_client,
        f"/api/internal/tether-versions/{version.id}/graph/",
        {"nodes": [{"id": "n1"}], "edges": []},  # node missing a valid kind
    )
    assert resp.status_code == 400
