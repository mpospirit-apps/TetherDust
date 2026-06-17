"""Tests for prefixed primary-key generation (engine.ids)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from engine.ids import generate_agt_id, generate_db_id, generate_id  # noqa: E402


def test_generate_id_has_prefix_and_entropy() -> None:
    value = generate_id("xyz")
    prefix, _, body = value.partition("_")
    assert prefix == "xyz"
    assert len(body) == 32
    assert all(c in "0123456789abcdef" for c in body)


def test_per_model_helpers_carry_their_prefix() -> None:
    assert generate_agt_id().startswith("agt_")
    assert generate_db_id().startswith("db_")


def test_ids_are_unique() -> None:
    ids = {generate_agt_id() for _ in range(2000)}
    assert len(ids) == 2000
