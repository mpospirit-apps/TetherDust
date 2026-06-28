"""Fixtures shared by the API tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def staff_client(auth_client: Any) -> Any:
    """A DRF client authenticated as a staff user (admin-console access)."""
    return auth_client(is_staff=True)
