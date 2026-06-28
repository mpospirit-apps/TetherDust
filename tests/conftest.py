"""Project-wide pytest fixtures and test-time environment.

Test configuration is read when ``pytest-django`` imports ``project.settings`` at
startup, which generally happens *before* this conftest's body runs — so the
canonical source is ``.env`` locally (it carries ``DJANGO_DEBUG=true``, a Fernet
``TETHERDUST_ENCRYPTION_KEY``, a ``DJANGO_SECRET_KEY`` and an
``INTERNAL_API_SERVICE_TOKEN``) and the matching CI secrets in CI. The
``setdefault`` block below is only a best-effort fallback for a bare environment
(and for setups where this file happens to load first); it cannot change settings
that were already imported.

Layout: pure-logic tests live under ``tests/unit`` (no DB); DB-backed tests use
the ``db`` fixture (pytest-django) and ``model_bakery`` for data. Keep Django
imports *inside* fixture bodies — at module import time the app registry is not
yet loaded.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet

# --- Test environment fallback (see module docstring) ------------------------
# ``setdefault`` leaves any real value (.env / CI secret / shell) untouched and
# only fills gaps for a bare environment; ``load_dotenv`` likewise does not
# override values already present in ``os.environ``.
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("TETHERDUST_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("INTERNAL_API_SERVICE_TOKEN", "test-internal-token")

import pytest  # noqa: E402

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from engine.models import Role
    from rest_framework.test import APIClient


# --- HTTP clients ------------------------------------------------------------


@pytest.fixture
def api_client() -> APIClient:
    """An unauthenticated DRF API client."""
    from rest_framework.test import APIClient

    return APIClient()


# --- Users / roles -----------------------------------------------------------
# A ``post_save`` signal on ``User`` auto-creates a ``UserProfile`` (see
# ``engine/signals.py``); these helpers work *with* it rather than creating a
# second profile.


@pytest.fixture
def make_role(db: object) -> Callable[..., Role]:
    """Factory for ``Role`` rows (M2M grants left empty unless wired by caller)."""
    from model_bakery import baker

    def _make(**kwargs: Any) -> Role:
        kwargs.setdefault("name", f"Role-{uuid.uuid4().hex[:8]}")
        return baker.make("engine.Role", **kwargs)

    return _make


@pytest.fixture
def make_user(db: object) -> Callable[..., User]:
    """Factory for ``User`` rows; assigns ``role`` onto the auto-created profile."""
    from django.contrib.auth.models import User

    def _make(
        *,
        role: Role | None = None,
        is_staff: bool = False,
        is_superuser: bool = False,
        password: str = "pw",
        username: str | None = None,
        **kwargs: Any,
    ) -> User:
        username = username or f"user-{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser,
            **kwargs,
        )
        if role is not None:
            # The signal already created a profile; just point it at the role.
            user.profile.role = role
            user.profile.save(update_fields=["role"])
        return user

    return _make


@pytest.fixture
def auth_client(make_user: Callable[..., User]) -> Callable[..., APIClient]:
    """Factory returning a DRF client authenticated as a (created) user.

    Pass ``user=`` to authenticate an existing user, or ``role=``/``is_staff=``
    to mint one. Uses ``force_authenticate`` so CSRF/session cookies are bypassed.
    """
    from rest_framework.test import APIClient

    def _make(user: User | None = None, **user_kwargs: Any) -> APIClient:
        if user is None:
            user = make_user(**user_kwargs)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _make


# --- Service registry override ----------------------------------------------


@pytest.fixture
def override_service() -> Any:
    """Swap a registry singleton for a fake, restoring the original afterwards.

    Usage::

        def test_x(override_service):
            fake = MagicMock(spec=PermissionService)
            override_service(PermissionService, fake)
    """
    from engine.services import registry

    saved: dict[type, object | None] = {}

    def _override(service_cls: type, fake: object) -> None:
        if service_cls not in saved:
            saved[service_cls] = registry._instances.get(service_cls)
        registry._instances[service_cls] = fake

    yield _override

    for service_cls, original in saved.items():
        if original is None:
            registry._instances.pop(service_cls, None)
        else:
            registry._instances[service_cls] = original
