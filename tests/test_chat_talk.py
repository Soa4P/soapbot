"""The conversation endpoint: POST /api/chat/messages.

Talk is the read-only boundary reversed on purpose, so the tests pin every gate the
feature must keep: the flag 404s the route, the runtime without a web adapter 503s,
the membership row decides who may talk, the session key is derived server-side, and
a halted pipeline with nothing to say is a 429 — never a fabricated reply.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from soapbot.accounts import create_owner, grant_membership
from soapbot.api.auth import require_api_auth
from soapbot.api.chat import router as chat_router
from soapbot.memory.db import Database
from soapbot.memory.store import MemoryStore


class _StubPipeline:
    """dispatch() stand-in with the two outcomes the endpoint can observe."""

    def __init__(self, memory: MemoryStore, *, reply: str = "好的，收到", halted: bool = False):
        self.memory = memory
        self.reply = reply
        self.halted = halted
        self.seen: list[SimpleNamespace] = []

    async def __call__(self, event):
        self.seen.append(event)
        # The pipeline archives the inbound row (PersistStage) and, after a successful
        # send, the reply (PersistReplyStage). Doing both here keeps the stub honest
        # about what the real path writes.
        await self.memory.archive_message(
            session_key=event.session_key,
            role="user",
            content=event.segments[0].data.get("text", ""),
            adapter="web",
            scene="private",
            user_id=event.sender.user_id,
            user_name=event.sender.nickname,
        )
        if self.reply:
            await self.memory.archive_message(
                session_key=event.session_key,
                role="assistant",
                content=self.reply,
                adapter="web",
                scene="private",
                user_name="soapbot",
            )
        return SimpleNamespace(
            model_reply=self.reply, halted=self.halted, halt_reason="quota" if self.halted else ""
        )


def _runtime(memory: MemoryStore, pipeline: _StubPipeline, *, with_adapter: bool = True):
    adapters = {"web": SimpleNamespace(meta=SimpleNamespace(name="web"))} if with_adapter else {}
    return SimpleNamespace(memory=memory, adapters=adapters, dispatch=pipeline)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'talk.db'}")
    await database.init()
    memory = MemoryStore(database)
    pipeline = _StubPipeline(memory)
    monkeypatch.setattr(
        "soapbot.app.get_runtime", lambda: _runtime(memory, pipeline)
    )
    # Talk on: every test here exists because of what the flag opens (or keeps shut).
    monkeypatch.setattr(
        "soapbot.api.chat.settings",
        SimpleNamespace(
            chat_web_enabled=True,
            chat_app_enabled=False,
            chat_desktop_enabled=False,
            chat_talk_enabled=True,
        ),
    )

    owner = await create_owner(database, username="alice", password="correct horse battery")

    app = FastAPI()
    app.include_router(chat_router)
    current = {"account": owner}

    async def fake_auth() -> dict[str, str]:
        account = current["account"]
        return {"subject": str(account.id), "role": account.role}

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            owner=owner,
            database=database,
            memory=memory,
            pipeline=pipeline,
        )
    await database.close()


async def test_flag_off_means_the_route_does_not_exist(env, monkeypatch) -> None:
    monkeypatch.setattr(
        "soapbot.api.chat.settings",
        SimpleNamespace(
            chat_web_enabled=True,
            chat_app_enabled=False,
            chat_desktop_enabled=False,
            chat_talk_enabled=False,
        ),
    )
    response = await env.client.post("/api/chat/messages", json={"content": "hello"})
    # 404, not 403: with talk off this deployment looks like it never had the route.
    assert response.status_code == 404
    assert env.pipeline.seen == []


async def test_runtime_without_the_web_adapter_is_503(env, monkeypatch) -> None:
    monkeypatch.setattr(
        "soapbot.app.get_runtime", lambda: _runtime(env.memory, env.pipeline, with_adapter=False)
    )
    response = await env.client.post("/api/chat/messages", json={"content": "hello"})
    assert response.status_code == 503
    assert env.pipeline.seen == []


async def test_owner_talks_and_both_rows_land_in_the_archive(env) -> None:
    response = await env.client.post("/api/chat/messages", json={"content": "在吗"})
    assert response.status_code == 200
    body = response.json()
    # The key is derived, not chosen: an account cannot name another session here.
    assert body["session_key"] == f"web:private:account-{env.owner.id}"
    assert body["reply"] == "好的，收到"

    page = await env.client.get(
        "/api/chat/messages",
        params={"session_key": body["session_key"], "latest": "true", "limit": 10},
    )
    rows = page.json()["messages"]
    assert [(row["role"], row["adapter"]) for row in rows] == [
        ("user", "web"),
        ("assistant", "web"),
    ]
    user_row = rows[0]
    assert user_row["content"] == "在吗"
    assert user_row["user_id"] == f"account-{env.owner.id}"
    assert user_row["user_name"] == "alice"


async def test_member_without_a_grant_gets_404(env) -> None:
    from soapbot.accounts import create_invite, redeem_invite

    code = await create_invite(env.database, created_by=env.owner.id)
    member = await redeem_invite(
        env.database, code=code, username="bob", password="correct horse battery"
    )
    env.current["account"] = member
    response = await env.client.post("/api/chat/messages", json={"content": "hello"})
    # Same shape as the read path: no membership row, no session, no existence leak.
    assert response.status_code == 404
    assert env.pipeline.seen == []


async def test_member_with_a_grant_can_talk(env) -> None:
    from soapbot.accounts import create_invite, redeem_invite

    code = await create_invite(env.database, created_by=env.owner.id)
    member = await redeem_invite(
        env.database, code=code, username="bob", password="correct horse battery"
    )
    await grant_membership(
        env.database,
        account_id=member.id,
        session_key=f"web:private:account-{member.id}",
        created_by=env.owner.id,
    )
    env.current["account"] = member
    response = await env.client.post("/api/chat/messages", json={"content": "你好"})
    assert response.status_code == 200
    assert response.json()["session_key"] == f"web:private:account-{member.id}"
    assert len(env.pipeline.seen) == 1


async def test_halted_pipeline_with_no_reply_is_429(env, monkeypatch) -> None:
    monkeypatch.setattr(
        "soapbot.app.get_runtime", lambda: _runtime(env.memory, _StubPipeline(env.memory, reply="", halted=True))
    )
    response = await env.client.post("/api/chat/messages", json={"content": "hello"})
    assert response.status_code == 429


async def test_blank_content_is_rejected_before_the_pipeline(env) -> None:
    """dispatch() skips the blank check that _on_event does for adapter events."""
    response = await env.client.post("/api/chat/messages", json={"content": "   "})
    assert response.status_code == 400
    assert env.pipeline.seen == []


@pytest.mark.parametrize("content", ["", "x" * 4001])
async def test_content_bounds_are_validated(env, content: str) -> None:
    response = await env.client.post("/api/chat/messages", json={"content": content})
    assert response.status_code == 422
    assert env.pipeline.seen == []


async def test_whitelist_admits_web_events_but_qq_private_stays_denied() -> None:
    """The exemption is scoped to the in-process web adapter, nothing else.

    The QQ private-deny default was a security fix; this test is the tripwire that
    notices if the web branch ever widens into a general private-chat bypass.
    """
    from soapbot.adapters.web import WebAdapter
    from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
    from soapbot.core.pipeline import PipelineContext
    from soapbot.core.stages import AccessPolicy, WhitelistStage

    def _event(adapter: str) -> IncomingMessage:
        return IncomingMessage(
            adapter=adapter,
            message_id=f"{adapter}-1",
            scene=MessageScene.PRIVATE,
            sender=Sender(user_id="account-3", nickname="someone"),
            segments=[MessageSegment.text("hi")],
        )

    stage = WhitelistStage(policy=AccessPolicy())
    web_ctx = PipelineContext(event=_event("web"), adapter=WebAdapter())
    result = await stage.run(web_ctx)
    assert not result.halt
    assert web_ctx.extras["memory_collect"] is True
    assert web_ctx.extras["replies_here"] is True

    # Empty policy = nobody may DM via a platform adapter; unchanged by the branch.
    qq_ctx = PipelineContext(event=_event("onebot11"), adapter=SimpleNamespace())
    result = await stage.run(qq_ctx)
    assert result.halt
    assert result.reason == "private_not_allowed"
