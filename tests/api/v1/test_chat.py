"""Public chat-support endpoints: session list/delete + prompts (live chat is WS)."""

from __future__ import annotations

from typing import Any

import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_sessions_denied_for_no_chat_role(auth_client: Any, make_role: Any) -> None:
    role = make_role(can_chat=False)
    assert auth_client(role=role).get("/api/v1/chat/sessions/").status_code == 403


def test_sessions_lists_own_with_messages(auth_client: Any, make_user: Any) -> None:
    user = make_user(is_staff=True)
    session = baker.make("engine.ChatSession", user=user, title="Hi")
    baker.make("engine.ChatMessage", session=session)  # only sessions with messages show

    resp = auth_client(user=user).get("/api/v1/chat/sessions/")
    assert resp.status_code == 200
    assert session.id in {s["id"] for s in resp.json()["sessions"]}


def test_session_delete_own(auth_client: Any, make_user: Any) -> None:
    user = make_user(is_staff=True)
    session = baker.make("engine.ChatSession", user=user)
    assert auth_client(user=user).delete(f"/api/v1/chat/sessions/{session.id}/").status_code == 204


def test_session_delete_other_users_404(auth_client: Any, make_user: Any) -> None:
    session = baker.make("engine.ChatSession", user=make_user())
    other = make_user(is_staff=True)
    assert auth_client(user=other).delete(f"/api/v1/chat/sessions/{session.id}/").status_code == 404


def test_prompts_lists_enabled(auth_client: Any) -> None:
    server = baker.make("engine.MCPServerConfiguration", is_active=True)
    baker.make(
        "engine.PromptConfiguration", mcp_server=server, is_enabled=True, prompt_name="explain"
    )
    resp = auth_client(is_staff=True).get("/api/v1/chat/prompts/")
    assert resp.status_code == 200
    assert any(p["name"] == "explain" for p in resp.json()["prompts"])
