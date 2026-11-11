"""Chat archive endpoints: isolation, cursor semantics, notes that go nowhere.

The isolation test is the point of the file. A member account must receive an empty
session list and a 404 for someone else's session, decided by the server — a UI that
hides a row is not a boundary.

Notes are tested for two things at once: the row lands with ``role="note"`` and
``adapter="web"``, and the response says ``delivered: False``. There is no adapter in
the fake runtime at all, so a call to ``send`` would raise instead of silently working.
"""

from __future__ import annotations

import json as _json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from soapbot.accounts import create_invite, create_owner, redeem_invite
from soapbot.api.auth import require_api_auth
from soapbot.api.chat import event_stream
from soapbot.api.chat import router as chat_router
from soapbot.memory.db import Database
from soapbot.memory.store import MemoryStore


@pytest.fixture
async def env(tmp_path, monkeypatch):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    await database.init()
    memory = MemoryStore(database)
    runtime = SimpleNamespace(memory=memory)
    monkeypatch.setattr("soapbot.app.get_runtime", lambda: runtime)

    for session in ("qq:group:1", "qq:group:2"):
        await memory.archive_message(
            session_key=session, role="user", content=f"hello from {session}", adapter="onebot11"
        )
        await memory.archive_message(
            session_key=session, role="assistant", content="hi", adapter="onebot11"
        )

    owner = await create_owner(database, username="alice", password="correct horse battery")
    code = await create_invite(database, created_by=owner.id, session_keys=("qq:group:1",))
    member = await redeem_invite(
        database, code=code, username="bob", password="correct horse battery"
    )

    app = FastAPI()
    app.include_router(chat_router)
    current = {"account": owner}

    async def fake_auth() -> dict[str, str]:
        account = current["account"]
        # ``subject`` is overridable so one test can present the bootstrap token, whose
        # subject is the literal string "operator" rather than a numeric account id.
        return {
            "subject": current.get("subject") or str(account.id),
            "role": current.get("role") or account.role,
        }

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            owner=owner,
            member=member,
            database=database,
            memory=memory,
        )
    await database.close()


async def test_owner_sees_every_session(env) -> None:
    response = await env.client.get("/api/chat/sessions")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "all"
    assert {row["session_key"] for row in body["sessions"]} == {"qq:group:1", "qq:group:2"}


async def test_member_sees_only_granted_sessions(env) -> None:
    env.current["account"] = env.member
    response = await env.client.get("/api/chat/sessions")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "member"
    assert [row["session_key"] for row in body["sessions"]] == ["qq:group:1"]


async def test_member_gets_404_for_an_ungranted_session(env) -> None:
    env.current["account"] = env.member
    response = await env.client.get("/api/chat/messages", params={"session_key": "qq:group:2"})
    assert response.status_code == 404
    # Not even the note endpoint, which is a write.
    response = await env.client.post(
        "/api/chat/notes", json={"session_key": "qq:group:2", "content": "peek"}
    )
    assert response.status_code == 404


async def test_messages_use_after_id_not_offset(env) -> None:
    first = await env.client.get(
        "/api/chat/messages", params={"session_key": "qq:group:1", "limit": 1}
    )
    assert first.status_code == 200
    page = first.json()
    assert len(page["messages"]) == 1
    cursor = page["next_after_id"]
    assert cursor == page["messages"][0]["id"]

    second = await env.client.get(
        "/api/chat/messages",
        params={"session_key": "qq:group:1", "after_id": cursor, "limit": 1},
    )
    assert second.json()["messages"][0]["id"] > cursor
    # No overlap between pages, which an offset would not guarantee under writes.
    assert second.json()["messages"][0]["id"] != cursor


async def test_a_note_is_archived_and_not_delivered(env) -> None:
    response = await env.client.post(
        "/api/chat/notes", json={"session_key": "qq:group:1", "content": "记住这个"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is False
    assert body["note"]["role"] == "note"
    assert body["note"]["adapter"] == "web"

    rows = await env.client.get(
        "/api/chat/messages", params={"session_key": "qq:group:1", "after_id": body["note"]["id"] - 1}
    )
    note = rows.json()["messages"][-1]
    assert note["content"] == "记住这个"
    assert note["role"] == "note"


async def test_empty_note_is_rejected(env) -> None:
    response = await env.client.post(
        "/api/chat/notes", json={"session_key": "qq:group:1", "content": "   "}
    )
    assert response.status_code == 400


async def test_stream_replays_the_backlog_from_the_cursor(env) -> None:
    """The generator is driven directly: an endless ASGI stream would hang teardown."""

    class _Connected:
        async def is_disconnected(self) -> bool:
            return False

    stream = event_stream(env.memory, _Connected(), "qq:group:1", 0)
    try:
        first = await stream.__anext__()
    finally:
        await stream.aclose()
    assert first.startswith("data: ")
    payload = _json.loads(first.removeprefix("data: "))
    assert payload["session_key"] == "qq:group:1"
    assert payload["role"] == "user"


async def test_every_surface_off_means_the_endpoint_disappears(env, monkeypatch) -> None:
    # Patched on the settings object, not the environment: ``.env`` is read by
    # pydantic-settings and never lands in ``os.environ``, so an env-only test would
    # pass while the real switch silently did nothing.
    monkeypatch.setattr(
        "soapbot.api.chat.settings",
        SimpleNamespace(chat_web_enabled=False, chat_app_enabled=False, chat_desktop_enabled=False),
    )
    response = await env.client.get("/api/chat/sessions")
    assert response.status_code == 404
    surfaces = await env.client.get("/api/chat/surfaces")
    assert surfaces.json() == {"web": False, "app": False, "desktop": False}


async def test_default_flags_leave_only_the_web_surface_on() -> None:
    """The shipped defaults, read from the real Settings class rather than a stub."""
    from soapbot.config import Settings

    defaults = Settings(_env_file=None)
    assert defaults.chat_web_enabled is True
    assert defaults.chat_app_enabled is False
    assert defaults.chat_desktop_enabled is False


async def test_the_bootstrap_token_cannot_read_the_archive(env) -> None:
    """The setup credential creates the first account; it is not an archive key."""
    env.current["subject"] = "operator"
    env.current["role"] = "owner"
    response = await env.client.get("/api/chat/sessions")
    assert response.status_code == 401
    assert response.json()["detail"] == "sign in with an account to read the archive"


async def test_a_member_grant_is_applied_before_the_limit(env) -> None:
    """Filtering after the query would hide an old grant behind newer sessions."""
    await env.memory.archive_message(
        session_key="qq:group:3", role="user", content="newest", adapter="onebot11"
    )
    rows = await env.memory.list_sessions(limit=1, session_keys=["qq:group:1"])
    assert [row["session_key"] for row in rows] == ["qq:group:1"]
