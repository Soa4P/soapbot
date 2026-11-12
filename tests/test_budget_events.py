"""The approval bus, and the QQ command path that must publish to it.

A notification is best-effort by design: the ledger transition commits first, so a
webhook that hangs or a QQ sender that is down must never turn a completed decision
into a 500 the operator retries. What matters is that every decision *origin*
publishes exactly one event, with the same payload the panel sees.
"""

from __future__ import annotations

import asyncio

import pytest

from soapbot.budget.commands import BudgetCommands
from soapbot.budget.events import (
    APPROVAL_BUS,
    APPROVED,
    DENIED,
    NOTIFY_TIMEOUT,
    REQUESTED,
    ApprovalBus,
    ApprovalEvent,
)
from soapbot.budget.policy import BudgetPolicy
from soapbot.budget.store import BudgetStore
from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.memory.db import Database
from soapbot.security.audit import AuditLog
from soapbot.security.principal import Principal, Role

SCOPE = "100"


@pytest.fixture(autouse=True)
def _clear_bus():
    APPROVAL_BUS.clear()
    yield
    APPROVAL_BUS.clear()


def _event(kind: str = REQUESTED) -> ApprovalEvent:
    return ApprovalEvent(
        kind=kind,
        request_id=1,
        session_key="onebot11:group:100",
        amount_minor=1250,
        currency="CNY",
        purpose="buy a book",
        requester_id="u1",
        created_at=1.0,
    )


# ------------------------------------------------------------------ bus itself


async def test_every_subscriber_sees_the_same_event() -> None:
    seen: list[ApprovalEvent] = []

    async def one(event):
        seen.append(event)

    async def two(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(one)
    unsubscribe = APPROVAL_BUS.subscribe(two)
    assert await APPROVAL_BUS.publish(_event()) == 2
    assert [e.kind for e in seen] == [REQUESTED, REQUESTED]

    unsubscribe()
    assert await APPROVAL_BUS.publish(_event(APPROVED)) == 1


async def test_a_failing_channel_does_not_break_the_decision_or_other_channels() -> None:
    seen: list[str] = []

    async def broken(event):
        raise RuntimeError("webhook returned 502 with the whole payload in the body")

    async def healthy(event):
        seen.append(event.kind)

    APPROVAL_BUS.subscribe(broken)
    APPROVAL_BUS.subscribe(healthy)
    assert await APPROVAL_BUS.publish(_event()) == 1
    assert seen == [REQUESTED]


async def test_a_hanging_channel_is_skipped(monkeypatch) -> None:
    monkeypatch.setattr("soapbot.budget.events.NOTIFY_TIMEOUT", 0.01)

    async def stuck(event):
        await asyncio.sleep(1)

    APPROVAL_BUS.subscribe(stuck)
    assert await APPROVAL_BUS.publish(_event()) == 0


def test_the_event_payload_is_an_explicit_whitelist() -> None:
    payload = _event().to_dict()
    assert set(payload) == {
        "kind",
        "request_id",
        "session_key",
        "amount_minor",
        "currency",
        "purpose",
        "requester_id",
        "requester_name",
        "actor_id",
        "actor_name",
        "note",
        "remaining_minor",
        "degraded",
        "created_at",
    }


def test_timeout_is_bounded() -> None:
    assert 0 < NOTIFY_TIMEOUT <= 10


# ------------------------------------------------------------------ command path


class _Adapter:
    name = "onebot11"


def _ctx(*, user_id: str = "u1", role: Role = Role.MEMBER) -> PipelineContext:
    principal = Principal(
        user_id=user_id,
        display_name=user_id,
        role=role,
        adapter="onebot11",
        scene="group",
        group_id=SCOPE,
        authenticated=True,
        source="config",
    )
    event = IncomingMessage(
        adapter="onebot11",
        message_id=f"m-{user_id}",
        scene=MessageScene.GROUP,
        sender=Sender(user_id=user_id, nickname=user_id),
        group_id=SCOPE,
        segments=[MessageSegment.text("/budget")],
        trace_id=f"t-{user_id}",
    )
    ctx = PipelineContext(event=event, adapter=_Adapter())  # type: ignore[arg-type]
    ctx.extras["principal"] = principal
    return ctx


@pytest.fixture
async def cmds(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    await database.init()
    store = BudgetStore(
        database,
        BudgetPolicy(period_cap_minor=10_000, per_request_cap_minor=5_000),
        audit=AuditLog(),
    )
    yield BudgetCommands(store, audit=AuditLog()), store
    await database.close()


async def test_a_request_publishes_once_and_a_dedup_resend_does_not_republish(cmds) -> None:
    commands, _store = cmds
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    reply = await commands.handle(_ctx(), ["12.50", "buy", "a", "book"])
    assert "已提交申请" in reply
    # Same caller, same text, same minute: the ledger deduplicates it. A notification
    # here would make one request look like two in every channel.
    await commands.handle(_ctx(), ["12.50", "buy", "a", "book"])
    assert [e.kind for e in seen] == [REQUESTED]
    assert seen[0].amount_minor == 1250
    assert seen[0].session_key.startswith("onebot11:group:")


async def test_a_command_decision_publishes_the_same_shape_as_the_panel(cmds) -> None:
    commands, store = cmds
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    await commands.handle(_ctx(), ["10", "materials"])
    pending = await store.list_pending(session_key=_ctx().event.session_key)
    request_id = pending[0].id

    await commands.handle(
        _ctx(user_id="u2", role=Role.OWNER), ["approve", str(request_id), "ok"]
    )
    assert [e.kind for e in seen] == [REQUESTED, APPROVED]
    assert seen[-1].actor_id == "u2"
    assert seen[-1].request_id == request_id
    assert seen[-1].degraded is False


async def test_a_denied_request_publishes_denied(cmds) -> None:
    commands, store = cmds
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    await commands.handle(_ctx(), ["10", "materials"])
    pending = await store.list_pending(session_key=_ctx().event.session_key)
    await commands.handle(_ctx(user_id="u2", role=Role.OWNER), ["deny", str(pending[0].id)])
    assert seen[-1].kind == DENIED


async def test_a_local_bus_can_be_used_without_the_global_singleton() -> None:
    bus = ApprovalBus()
    seen: list[int] = []

    async def capture(event):
        seen.append(event.request_id)

    bus.subscribe(capture)
    assert await bus.publish(_event()) == 1
    assert seen == [1]
