"""Every engine model mints a prefixed ULID-style id (``<prefix>_<32 hex>``).

This guards the ``__prefix__`` ↔ ``default=generate_<prefix>_id`` wiring: a model
pointed at the wrong generator (a copy-paste slip) would mint someone else's
prefix and fail here.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.apps import apps
from model_bakery import baker

pytestmark = pytest.mark.django_db

# ``UserProfile`` is created by a ``post_save`` signal on ``User``; letting baker
# build one conflicts with that auto-created row, so it is checked separately.
_SPECIAL = {"UserProfile"}

_MODELS = [
    model
    for model in apps.get_app_config("engine").get_models()
    if hasattr(model, "__prefix__") and model.__name__ not in _SPECIAL
]


@pytest.mark.parametrize("model", _MODELS, ids=lambda m: m.__name__)
def test_model_mints_its_prefix(model: type) -> None:
    obj = baker.make(model)
    assert obj.pk.startswith(f"{model.__prefix__}_")
    prefix, _, body = obj.pk.partition("_")
    assert len(body) == 32


def test_user_profile_prefix(make_user: Any) -> None:
    user = make_user()
    assert user.profile.pk.startswith("usp_")
