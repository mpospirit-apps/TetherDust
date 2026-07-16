"""Codebase URL parsing and tree flattening (``engine.integrations.github_client``)."""

from __future__ import annotations

import pytest
from engine.integrations.github_client import filter_tree, parse_owner_repo


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
        ("http://github.com/owner/repo/tree/main", ("owner", "repo")),
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("github.com/owner/repo", ("owner", "repo")),
    ],
)
def test_parse_owner_repo_valid(url: str, expected: tuple[str, str]) -> None:
    assert parse_owner_repo(url) == expected


@pytest.mark.parametrize("url", ["", "https://github.com/owner", "not-a-url", "owner"])
def test_parse_owner_repo_invalid(url: str) -> None:
    with pytest.raises(ValueError):
        parse_owner_repo(url)


@pytest.fixture
def tree() -> list[dict[str, object]]:
    return [
        {"path": "src/app.py", "type": "blob", "size": 100},
        {"path": "src/util.py", "type": "blob", "size": 50},
        {"path": "README.md", "type": "blob", "size": 10},
        {"path": "src", "type": "tree"},
    ]


def test_filter_tree_drops_trees(tree: list[dict[str, object]]) -> None:
    result = filter_tree(tree)
    assert {e["path"] for e in result} == {"src/app.py", "src/util.py", "README.md"}
    assert all(e["type"] == "file" for e in result)
