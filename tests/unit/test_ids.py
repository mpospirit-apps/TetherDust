"""Prefixed primary-key generation (``engine.ids``).

Beyond the generic generator, every model owns a ``generate_<prefix>_id``
helper. We introspect the module and assert each one mints *its own* prefix —
a copy-paste bug (e.g. ``generate_db_id`` delegating to ``generate_id("agt")``)
would surface here rather than as mislabelled IDs in production.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from engine import ids

# {helper_name: function} for every generate_<prefix>_id except the generic one.
_GENERATORS: dict[str, Callable[[], str]] = {
    name: fn
    for name, fn in vars(ids).items()
    if callable(fn)
    and name.startswith("generate_")
    and name.endswith("_id")
    and name != "generate_id"
}

_HEX32 = re.compile(r"[0-9a-f]{32}")


def test_generate_id_format() -> None:
    prefix, _, body = ids.generate_id("xyz").partition("_")
    assert prefix == "xyz"
    assert _HEX32.fullmatch(body)  # 128 bits of lowercase hex


@pytest.mark.parametrize("name", sorted(_GENERATORS))
def test_helper_carries_its_own_prefix(name: str) -> None:
    expected = name.removeprefix("generate_").removesuffix("_id")
    prefix, _, body = _GENERATORS[name]().partition("_")
    assert prefix == expected
    assert _HEX32.fullmatch(body)


def test_ids_are_unique() -> None:
    assert len({ids.generate_agt_id() for _ in range(2000)}) == 2000
