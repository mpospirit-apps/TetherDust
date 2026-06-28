"""Public docs API — role scoping, content reads, and the path guard."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _docs_dir(settings: Any, tmp_path: Any) -> Any:
    # Point the documentations root at a temp dir so file-tree builds are isolated
    # (seeded sources resolve to non-existent folders → empty trees).
    settings.TETHERDUST_DOCUMENTATIONS_DIR = str(tmp_path)
    return tmp_path


def test_sources_denied_without_access(auth_client: Any) -> None:
    assert auth_client().get("/api/v1/docs/sources/").status_code == 403


def test_sources_staff(staff_client: Any) -> None:
    baker.make("engine.DocumentationSource", is_active=True, folder_name="myfolder")
    resp = staff_client.get("/api/v1/docs/sources/")
    assert resp.status_code == 200
    assert any(s["name"] == "myfolder" for s in resp.json()["sources"])


def test_content_requires_params(staff_client: Any) -> None:
    assert staff_client.get("/api/v1/docs/content/").status_code == 400


def test_content_source_not_found(staff_client: Any) -> None:
    resp = staff_client.get("/api/v1/docs/content/?source=nope&path=x.md")
    assert resp.status_code == 404


def test_content_reads_markdown_file(staff_client: Any, _docs_dir: Any) -> None:
    folder = _docs_dir / "guide"
    folder.mkdir()
    (folder / "intro.md").write_text("# Hello", encoding="utf-8")
    baker.make("engine.DocumentationSource", is_active=True, folder_name="guide")

    resp = staff_client.get("/api/v1/docs/content/?source=guide&path=intro.md")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_markdown"] is True
    assert body["content"] == "# Hello"
