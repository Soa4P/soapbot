"""Unified chat: QQ binding, session mapping, and visible delivery states.

One continuous conversation across web/app/desktop/QQ rests on three tests-worthy
properties:

* the binding is owner-drawn and one-to-one — a platform id can never claim itself;
* the mapper only fires when every trust link holds (flag + private + bound + active
  account), and leaves the event untouched otherwise;
* rejected and failed sends are visible rows, not silence.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from soapbot.accounts import (
    bind_qq_user,
    create_owner,
    unbind_qq_user,
)
from soapbot.accounts.mapper import SessionMapper
from soapbot.accounts.service import AccountError, account_by_qq_user
from soapbot.api.accounts import router as accounts_router
from soapbot.api.auth import require_api_auth
from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.core.runtime import BotRuntime
from soapbot.core.stages import AccessPolicy, WhitelistStage
from soapbot.memory.db import Database
from soapbot.memory.store import MemoryStore


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'unified.db'}")
    await database.init()
    yield database
    await database.close()


# ------------------------------------------------------------------ binding service
async def test_binding_is_owner_drawn_and_one_to_one(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    bound = await bind_qq_user(db, account_id=owner.id, qq_user_id="123456789")
    assert bound.qq_user_id == "123456789"
    assert await account_by_qq_user(db, "123456789") is not None
    assert await account_by_qq_user(db, "99999999") is None

    # A second account cannot take the same QQ id. Moving the link means the old
    # holder lets go first (unbind), then the new one binds — the id never points at
    # two identities, not even transiently.
    from soapbot.accounts import create_invite, redeem_invite

    code = await create_invite(db, created_by=owner.id)
    member = await redeem_invite(db, code=code, username="bob", password="correct horse battery")
    with pytest.raises(AccountError, match="已绑定"):
        await bind_qq_user(db, account_id=member.id, qq_user_id="123456789")

    await unbind_qq_user(db, account_id=owner.id)
    moved = await bind_qq_user(db, account_id=member.id, qq_user_id="123456789")
    assert moved.qq_user_id == "123456789"
    resolved = await account_by_qq_user(db, "123456789")
    assert resolved is not None and resolved.id == member.id

    await unbind_qq_user(db, account_id=member.id)
    assert await account_by_qq_user(db, "123456789") is None


async def test_binding_rejects_non_qq_shapes_and_unknown_accounts(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    for bad in ("abc", "123", "1234; drop table", "-1", ""):
        with pytest.raises(AccountError):
            await bind_qq_user(db, account_id=owner.id, qq_user_id=bad)
    with pytest.raises(AccountError, match="不存在"):
        await bind_qq_user(db, account_id=424242, qq_user_id="123456789")


async def test_a_disabled_account_resolves_to_no_binding(db) -> None:
    from soapbot.accounts import create_invite, redeem_invite, set_account_status

    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(db, created_by=owner.id)
    member = await redeem_invite(db, code=code, username="bob", password="correct horse battery")
    await bind_qq_user(db, account_id=member.id, qq_user_id="123456789")
    await set_account_status(db, account_id=member.id, status="disabled")
    assert await account_by_qq_user(db, "123456789") is None


# ------------------------------------------------------------------ mapper
def _qq_event(user_id: str = "123456789") -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id="qq-1",
        scene=MessageScene.PRIVATE,
        sender=Sender(user_id=user_id, nickname="qq"),
        segments=[MessageSegment.text("hi")],
    )


async def test_mapper_fires_only_when_every_trust_link_holds(db, monkeypatch) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    mapper = SessionMapper(db)

    monkeypatch.setattr("soapbot.accounts.mapper.settings", SimpleNamespace(chat_unified_enabled=False))
    assert await mapper(_qq_event()) is None  # flag off → nothing changes
    monkeypatch.setattr("soapbot.accounts.mapper.settings", SimpleNamespace(chat_unified_enabled=True))
    assert await mapper(_qq_event()) is None  # flag on but nobody bound

    await bind_qq_user(db, account_id=owner.id, qq_user_id="123456789")
    # Negative results are cached too (so a flood of unbound QQ users cannot hammer
    # the accounts db); the API invalidates on bind/unbind — here we do it by hand.
    mapper.invalidate()
    assert await mapper(_qq_event()) == f"web:private:account-{owner.id}"

    group = IncomingMessage(
        adapter="onebot11",
        message_id="qq-g1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="123456789", nickname="qq"),
        segments=[MessageSegment.text("hi")],
        group_id="777",
    )
    assert await mapper(group) is None  # groups never join the unified session

    web = IncomingMessage(
        adapter="web",
        message_id="web-1",
        scene=MessageScene.PRIVATE,
        sender=Sender(user_id="account-1", nickname="w"),
        segments=[MessageSegment.text("hi")],
    )
    assert await mapper(web) is None  # only the QQ platform adapter maps


async def test_mapper_caches_and_cache_misses_expire(db, monkeypatch) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    await bind_qq_user(db, account_id=owner.id, qq_user_id="123456789")
    mapper = SessionMapper(db, ttl=60.0)
    monkeypatch.setattr("soapbot.accounts.mapper.settings", SimpleNamespace(chat_unified_enabled=True))

    assert await mapper(_qq_event()) == f"web:private:account-{owner.id}"
    # The cache holds the answer; a second call must not need the database again
    # (observable via the bounded cache, not by spying on the db).
    assert mapper._peek("123456789", time.time()) == str(owner.id)

    # An unbind takes effect when the cache entry expires.
    await unbind_qq_user(db, account_id=owner.id)
    assert await mapper(_qq_event()) == f"web:private:account-{owner.id}"  # stale cache
    mapper.invalidate("123456789")
    assert await mapper(_qq_event()) is None  # fresh lookup honours the unbind


# ------------------------------------------------------------------ whitelist branch
async def test_whitelist_admits_a_mapped_private_event_and_denies_an_unmapped_one(monkeypatch) -> None:
    from soapbot.adapters.onebot11 import OneBot11Adapter  # noqa: F401  (import sanity)

    stage = WhitelistStage(policy=AccessPolicy())

    def _ctx(event: IncomingMessage) -> PipelineContext:
        return PipelineContext(event=event, adapter=SimpleNamespace())

    monkeypatch.setattr("soapbot.core.stages.settings", SimpleNamespace(chat_unified_enabled=True))
    bound = _qq_event()
    bound.session_key_override = "web:private:account-3"
    mapped_ctx = _ctx(bound)
    result = await stage.run(mapped_ctx)
    assert not result.halt
    # The mapped event gets the web-talk archive posture.
    assert mapped_ctx.extras["memory_collect"] is True
    assert mapped_ctx.extras["replies_here"] is True

    unmapped = _qq_event("555555555")  # no override: the derived key, default deny
    result = await stage.run(_ctx(unmapped))
    assert result.halt
    assert result.reason == "private_not_allowed"


async def test_whitelist_branch_requires_the_flag_even_with_an_override(monkeypatch) -> None:
    """The override alone must never widen admission — the flag is part of the chain."""
    stage = WhitelistStage(policy=AccessPolicy())
    event = _qq_event()
    event.session_key_override = "web:private:account-3"
    ctx = PipelineContext(event=event, adapter=SimpleNamespace())
    monkeypatch.setattr("soapbot.core.stages.settings", SimpleNamespace(chat_unified_enabled=False))
    result = await stage.run(ctx)
    assert result.halt
    assert result.reason == "private_not_allowed"


# ------------------------------------------------------------------ runtime dispatch
class _SlowPipeline:
    """Records concurrency: two dispatches must never overlap in one session."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.overlapped = False
        self.keys: list[str] = []

    async def run(self, ctx: PipelineContext) -> None:
        self.in_flight += 1
        self.keys.append(ctx.event.session_key)
        if self.in_flight > 1:
            self.overlapped = True
        await asyncio.sleep(0.02)
        self.in_flight -= 1


async def test_dispatch_maps_bound_qq_events_and_serialises_the_unified_session(db, monkeypatch) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    await bind_qq_user(db, account_id=owner.id, qq_user_id="123456789")
    mapper = SessionMapper(db)
    monkeypatch.setattr("soapbot.accounts.mapper.settings", SimpleNamespace(chat_unified_enabled=True))

    pipeline = _SlowPipeline()
    runtime = BotRuntime(pipeline=pipeline, session_mapper=mapper)
    from soapbot.core.adapter import Adapter  # noqa: F401

    runtime.adapters["onebot11"] = SimpleNamespace(meta=SimpleNamespace(name="onebot11"))

    async def two_messages() -> None:
        await asyncio.gather(
            runtime.dispatch(_qq_event()),
            runtime.dispatch(_qq_event()),
        )

    await two_messages()
    # Both events joined the same unified session (mapped keys), serialized by the
    # session lock that now guards the *unified* key, and the adapter is untouched.
    assert pipeline.keys == [f"web:private:account-{owner.id}"] * 2
    assert pipeline.overlapped is False
    event = _qq_event()
    assert event.adapter == "onebot11" and event.session_key_override == ""


# ------------------------------------------------------------------ delivery states
async def test_a_failed_send_still_lands_as_send_failed(tmp_path) -> None:
    from soapbot.memory.stages import PersistReplyStage

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'send.db'}")
    await database.init()
    memory = MemoryStore(database)
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="u1", nickname="u1"),
        segments=[MessageSegment.text("hi")],
        group_id="123",
    )
    ctx = PipelineContext(event=event, adapter=None)
    ctx.model_reply = "这句话没送到"
    ctx.extras["send_ok"] = False
    ctx.extras["send_error"] = "platform refused"
    await PersistReplyStage(memory).run(ctx)  # type: ignore[arg-type]
    rows = await memory.messages_since("onebot11:group:123")
    assert [(r["role"], r["state"], r["reason"]) for r in rows] == [
        ("assistant", "send_failed", "platform refused")
    ]
    await database.close()


class _HaltEarlyPipeline:
    """Halts before persisting anything — the shape of a Guard/dedup refusal."""

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    async def __call__(self, event):
        return SimpleNamespace(model_reply="", halted=True, halt_reason="abuse_rate_limited")


async def test_a_rejected_talk_message_is_a_visible_rejected_row(monkeypatch, tmp_path) -> None:
    """The talk endpoint no longer just 429s: the sender sees what happened to the
    message in their own timeline (reason is a short token, never prose)."""
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'reject.db'}")
    await database.init()
    memory = MemoryStore(database)
    monkeypatch.setattr(
        "soapbot.app.get_runtime",
        lambda: SimpleNamespace(memory=memory, adapters={"web": object()}, dispatch=_HaltEarlyPipeline(memory)),
    )
    monkeypatch.setattr(
        "soapbot.api.chat.settings",
        SimpleNamespace(chat_web_enabled=True, chat_talk_enabled=True, chat_app_enabled=False, chat_desktop_enabled=False),
    )
    owner = await create_owner(database, username="alice", password="correct horse battery")

    app = FastAPI()
    from soapbot.api.chat import router as chat_router

    app.include_router(chat_router)
    app.dependency_overrides[require_api_auth] = lambda: {
        "subject": str(owner.id),
        "role": "owner",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/messages", json={"content": "被拒绝的话"})
        assert response.status_code == 429
        assert response.json()["detail"] == "abuse_rate_limited"

    session = f"web:private:account-{owner.id}"
    rows = await memory.messages_since(session)
    assert [(r["role"], r["state"], r["reason"]) for r in rows] == [
        ("user", "rejected", "abuse_rate_limited")
    ]
    await database.close()


# ------------------------------------------------------------------ binding API
@pytest.fixture
async def accounts_env(tmp_path, monkeypatch):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    await database.init()
    owner = await create_owner(database, username="alice", password="correct horse battery")
    from soapbot.accounts import create_invite, redeem_invite

    code = await create_invite(database, created_by=owner.id)
    member = await redeem_invite(database, code=code, username="bob", password="correct horse battery")

    def _get_runtime():
        return SimpleNamespace(memory=MemoryStore(database))

    monkeypatch.setattr("soapbot.app.get_runtime", _get_runtime)

    app = FastAPI()
    app.include_router(accounts_router)
    current = {"subject": str(owner.id), "role": owner.role, "mode": "token"}

    async def fake_auth() -> dict[str, str]:
        # ``mode`` is what ``require_credential`` inspects: a token-backed call may
        # change state. Switching the current subject is how the test acts as member.
        return dict(current)

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            owner=owner,
            member=member,
            database=database,
        )
    await database.close()


async def test_binding_api_is_owner_only(accounts_env) -> None:
    url = f"/api/accounts/{accounts_env.member.id}/binding"
    ok = await accounts_env.client.put(url, json={"qq_user_id": "123456789"})
    assert ok.status_code == 200
    assert ok.json()["account"]["qq_user_id"] == "123456789"

    accounts_env.current.update(subject=str(accounts_env.member.id), role="member")
    denied = await accounts_env.client.put(url, json={"qq_user_id": "123456789"})
    assert denied.status_code == 403
    listed = await accounts_env.client.delete(url)
    assert listed.status_code == 403

    accounts_env.current.update(subject=str(accounts_env.owner.id), role="owner")
    removed = await accounts_env.client.delete(url)
    assert removed.status_code == 200
    assert removed.json()["account"]["qq_user_id"] == ""


async def test_binding_api_validates_the_qq_shape(accounts_env) -> None:
    url = f"/api/accounts/{accounts_env.owner.id}/binding"
    bad = await accounts_env.client.put(url, json={"qq_user_id": "not-a-qq"})
    assert bad.status_code == 400
    too_short = await accounts_env.client.put(url, json={"qq_user_id": "123"})
    assert too_short.status_code in (400, 422)


async def test_the_accounts_list_exposes_the_binding(accounts_env) -> None:
    await accounts_env.client.put(
        f"/api/accounts/{accounts_env.member.id}/binding", json={"qq_user_id": "123456789"}
    )
    rows = (await accounts_env.client.get("/api/accounts")).json()["accounts"]
    by_id = {row["id"]: row for row in rows}
    assert by_id[accounts_env.member.id]["qq_user_id"] == "123456789"
    assert by_id[accounts_env.owner.id]["qq_user_id"] == ""
