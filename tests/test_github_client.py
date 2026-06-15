"""Tests for codebase URL parsing and tree glob filtering.

The integration module has no Django imports at load time, so these tests need
no Django setup (matching the rest of the suite).
"""

import sys
from pathlib import Path

import pytest

# The integration module lives in the Django web app; add it to the path.
WEB_DIR = Path(__file__).resolve().parent.parent / "tetherdust" / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from core.integrations.github_client import (  # noqa: E402
    filter_tree,
    matches_any,
    parse_owner_repo,
)


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


def _tree() -> list[dict[str, object]]:
    return [
        {"path": "src/app.py", "type": "blob", "size": 100},
        {"path": "src/util.py", "type": "blob", "size": 50},
        {"path": "README.md", "type": "blob", "size": 10},
        {"path": "node_modules/x/index.js", "type": "blob", "size": 5},
        {"path": "package-lock.json", "type": "blob", "size": 999},
        {"path": "src", "type": "tree"},
    ]


def test_filter_tree_drops_trees_and_excludes() -> None:
    result = filter_tree(_tree(), exclude_globs=["node_modules/*", "*.json"])
    assert {e["path"] for e in result} == {"src/app.py", "src/util.py", "README.md"}
    assert all(e["type"] == "file" for e in result)


def test_filter_tree_include_only() -> None:
    result = filter_tree(_tree(), include_globs=["*.py"])
    assert {e["path"] for e in result} == {"src/app.py", "src/util.py"}


def test_filter_tree_subpath_relativizes() -> None:
    result = filter_tree(_tree(), subpath="src")
    assert {e["path"] for e in result} == {"app.py", "util.py"}


def test_matches_any_nested_and_basename() -> None:
    assert matches_any("a/b/node_modules/x.js", ["node_modules/*"])
    assert matches_any("deep/path/file.lock", ["*.lock"])
    assert not matches_any("src/app.py", ["*.md"])
