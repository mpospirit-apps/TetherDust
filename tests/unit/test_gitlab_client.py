"""GitLab project-path parsing (``engine.integrations.gitlab_client``)."""

from __future__ import annotations

import pytest
from engine.integrations.gitlab_client import parse_gitlab_path


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://gitlab.com/group/project", "group/project"),
        ("https://gitlab.com/group/subgroup/project", "group/subgroup/project"),
        ("https://gitlab.com/group/project.git", "group/project"),
        ("https://gitlab.com/group/project/", "group/project"),
        ("https://gitlab.com/group/project/-/tree/main", "group/project"),
        ("https://gitlab.com/group/subgroup/project/-/blob/main/x.py", "group/subgroup/project"),
        ("git@gitlab.com:group/project.git", "group/project"),
        ("gitlab.com/group/project", "group/project"),
    ],
)
def test_parse_gitlab_path_valid(url: str, expected: str) -> None:
    assert parse_gitlab_path(url) == expected


@pytest.mark.parametrize("url", ["", "https://gitlab.com/group", "not-a-url", "group"])
def test_parse_gitlab_path_invalid(url: str) -> None:
    with pytest.raises(ValueError):
        parse_gitlab_path(url)
