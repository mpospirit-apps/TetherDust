"""PermissionService — role-based access resolution.

The contract (see the service docstring): ``None`` means *unrestricted* (staff or
an admin role); an empty set / ``.none()`` queryset means *no access*; otherwise
the user sees exactly what their role grants, filtered to enabled/active rows.
"""

from __future__ import annotations

from typing import Any

import pytest
from engine.services import PermissionService, get
from model_bakery import baker

pytestmark = pytest.mark.django_db


@pytest.fixture
def perms() -> PermissionService:
    return get(PermissionService)


# --- unrestricted (staff / admin role) --------------------------------------


def test_staff_is_unrestricted(perms: PermissionService, make_user: Any) -> None:
    profile = make_user(is_staff=True).profile
    assert perms.get_allowed_tools(profile) is None
    assert perms.get_allowed_databases(profile) is None
    assert perms.get_allowed_doc_sources(profile) is None
    assert perms.get_max_row_limit(profile) is None
    assert perms.can_chat(profile) is True


def test_admin_role_is_unrestricted(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    profile = make_user(role=make_role(is_admin_role=True)).profile
    assert perms.get_allowed_tools(profile) is None
    assert perms.get_allowed_databases(profile) is None
    assert perms.can_chat(profile) is True


def test_admin_role_can_chat_even_with_flag_off(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    role = make_role(is_admin_role=True, can_chat=False)
    profile = make_user(role=role).profile
    assert perms.can_chat(profile) is True


# --- no role (deny all) ------------------------------------------------------


def test_no_role_denies_everything(perms: PermissionService, make_user: Any) -> None:
    profile = make_user().profile
    assert perms.get_allowed_tools(profile) == set()
    assert perms.get_allowed_databases(profile) == set()
    assert perms.get_allowed_doc_sources(profile) == set()
    assert perms.get_max_row_limit(profile) == 100  # default floor
    assert perms.can_chat(profile) is False
    assert perms.get_allowed_reports(profile).count() == 0


# --- role-scoped grants ------------------------------------------------------


def test_allowed_tools_filters_disabled_and_inactive_server(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    # Custom (non-builtin) tool names: the builtin tools are seeded into every
    # test DB by ``engine.apps`` post_migrate, and ``tool_name`` is unique.
    role = make_role()
    active_server = baker.make("engine.MCPServerConfiguration", is_active=True)
    inactive_server = baker.make("engine.MCPServerConfiguration", is_active=False)
    enabled = baker.make(
        "engine.ToolConfiguration", mcp_server=active_server, is_enabled=True, tool_name="custom_a"
    )
    disabled = baker.make(
        "engine.ToolConfiguration", mcp_server=active_server, is_enabled=False, tool_name="custom_b"
    )
    on_inactive = baker.make(
        "engine.ToolConfiguration",
        mcp_server=inactive_server,
        is_enabled=True,
        tool_name="custom_c",
    )
    role.allowed_tools.set([enabled, disabled, on_inactive])

    profile = make_user(role=role).profile
    assert perms.get_allowed_tools(profile) == {"custom_a"}


def test_allowed_databases_filters_inactive(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    role = make_role()
    active = baker.make("engine.DatabaseConnection", is_active=True, name="analytics")
    inactive = baker.make("engine.DatabaseConnection", is_active=False, name="legacy")
    role.allowed_databases.set([active, inactive])

    profile = make_user(role=role).profile
    assert perms.get_allowed_databases(profile) == {"analytics"}


def test_max_row_limit_from_role(perms: PermissionService, make_user: Any, make_role: Any) -> None:
    profile = make_user(role=make_role(max_row_limit=500)).profile
    assert perms.get_max_row_limit(profile) == 500


def test_can_chat_respects_role_flag(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    assert perms.can_chat(make_user(role=make_role(can_chat=False)).profile) is False
    assert perms.can_chat(make_user(role=make_role(can_chat=True)).profile) is True


# --- resource scoping (reports / dashboards / tethers) ----------------------


def test_allowed_reports_scoped_to_role(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    role = make_role()
    other = make_role()
    mine = baker.make("engine.ReportDefinition", is_active=True)
    mine.allowed_roles.set([role])
    theirs = baker.make("engine.ReportDefinition", is_active=True)
    theirs.allowed_roles.set([other])
    inactive = baker.make("engine.ReportDefinition", is_active=False)
    inactive.allowed_roles.set([role])

    profile = make_user(role=role).profile
    assert set(perms.get_allowed_reports(profile)) == {mine}
    assert perms.can_view_reports(profile) is True


def test_can_view_tethers_requires_role_flag(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    role_off = make_role(can_view_tethers=False)
    tether = baker.make("engine.Tether", is_active=True)
    tether.allowed_roles.set([role_off])
    assert perms.can_view_tethers(make_user(role=role_off).profile) is False

    role_on = make_role(can_view_tethers=True)
    tether2 = baker.make("engine.Tether", is_active=True)
    tether2.allowed_roles.set([role_on])
    assert perms.can_view_tethers(make_user(role=role_on).profile) is True


def test_can_view_docs_nonstaff(perms: PermissionService, make_user: Any, make_role: Any) -> None:
    assert perms.can_view_docs(make_user().profile) is False  # no role
    role = make_role()
    doc = baker.make("engine.DocumentationSource", is_active=True)
    role.allowed_doc_sources.set([doc])
    assert perms.can_view_docs(make_user(role=role).profile) is True


# --- name/id projections for MCP filter registration ------------------------


def test_filter_names_are_none_for_staff(perms: PermissionService, make_user: Any) -> None:
    profile = make_user(is_staff=True).profile
    assert perms.get_allowed_reports_names(profile) is None
    assert perms.get_allowed_tethers_ids(profile) is None


def test_allowed_tether_ids_are_strings(
    perms: PermissionService, make_user: Any, make_role: Any
) -> None:
    role = make_role()
    tether = baker.make("engine.Tether", is_active=True)
    tether.allowed_roles.set([role])
    profile = make_user(role=role).profile
    assert perms.get_allowed_tethers_ids(profile) == {tether.id}
