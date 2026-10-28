"""``/budget`` command surface: authorisation, scope pinning, and failure modes.

The threat model here is different from the ledger's
---------------------------------------------------
``test_wave5_budget.py`` proves the *accounting* is right. This file proves the
*command* cannot be talked into doing something the ledger's own guarantees would
then faithfully record:

* a member cannot approve, even by guessing the sub-command name
* the scope comes from the event, never from an argument
* a request without a purpose is refused (the approver must know what they are
  authorising)
* one group's request id is invisible from another group
* a double-tapped command reserves once
"""

from __future__ import annotations

import pytest

from soapbot.budget.commands import BudgetCommands
from soapbot.budget.policy import BudgetPolicy
from soapbot.budget.store import BudgetStore
from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.memory.db import Database
from soapbot.security.audit import AuditLog
from soapbot.security.principal import Principal, Role

SCOPE_GROUP = "100"
OTHER_GROUP = "200"


class _Adapter:
    """Minimal adapter: commands never touch it."""

    name = "onebot11"


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'cmd.db'}")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
async def cmds(db):
    store = BudgetStore(
        db,
        BudgetPolicy(period_cap_minor=10_000, per_request_cap_minor=5_000),
        audit=AuditLog(),
    )
    return BudgetCommands(store, audit=AuditLog())


def _ctx(
    *, user_id="u1", role=Role.MEMBER, group_id=SCOPE_GROUP, authenticated=True
) -> PipelineContext:
    """Build a context whose scope comes from the event, as in production.

    ``session_key`` is a derived property on ``IncomingMessage``, so the only way
    to place a caller in a scope is to set ``group_id`` — which is exactly the
    property under test (a command argument cannot move it).
    """
    principal = Principal(
        user_id=user_id,
        display_name=user_id,
        role=role,
        adapter="onebot11",
        scene="group",
        group_id=group_id,
        authenticated=authenticated,
        source="config",
    )
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m-1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id=user_id, nickname=user_id),
        group_id=group_id,
        segments=[MessageSegment.text("/budget")],
        trace_id="t-1",
    )
    ctx = PipelineContext(event=event, adapter=_Adapter())  # type: ignore[arg-type]
    ctx.extras["principal"] = principal
    return ctx


# ------------------------------------------------------------------- viewing


async def test_empty_budget_shows_the_cap(cmd_dispatch):
    reply = await cmd_dispatch(_ctx(), [])
    assert "额度" in reply
    assert "100.00" in reply


async def test_usage_is_reflected(cmd_dispatch):
    ctx = _ctx()
    await cmd_dispatch(ctx, ["25", "买资料"])
    reply = await cmd_dispatch(ctx, [])
    assert "25.00" in reply
    assert "待批" in reply


# ----------------------------------------------------------------- requests


async def test_member_can_request(cmd_dispatch):
    reply = await cmd_dispatch(_ctx(), ["25.5", "买资料"])
    assert "已提交申请" in reply
    assert "25.50" in reply
    # The reply must tell the requester what happens next.
    assert "approve" in reply


async def test_request_without_purpose_is_refused(cmd_dispatch):
    """An approver cannot consent to an unlabelled transfer of quota."""
    reply = await cmd_dispatch(_ctx(), ["25.5"])
    assert "用途" in reply


async def test_request_rejects_junk_amount(cmd_dispatch):
    reply = await cmd_dispatch(_ctx(), ["abc", "买资料"])
    assert "金额" in reply


async def test_request_over_per_request_cap_is_refused(cmd_dispatch):
    reply = await cmd_dispatch(_ctx(), ["999", "买资料"])
    assert "单笔上限" in reply or "申请未受理" in reply


async def test_double_tap_reserves_once(cmd_dispatch, db):
    ctx = _ctx()
    first = await cmd_dispatch(ctx, ["25", "买资料"])
    second = await cmd_dispatch(ctx, ["25", "买资料"])
    assert "已提交申请" in first
    # Same minute, same amount, same purpose -> recognised as the same intent.
    assert "已经" in second or "无需重复" in second


# ---------------------------------------------------------------- authority


async def test_member_cannot_approve(cmd_dispatch):
    """Guessing the sub-command name must not be enough.

    ``/budget`` itself is a USE_COMMAND command; the decision sub-commands
    re-check APPROVE_PAYMENT. Without that second check, every member could
    approve their own group's spend.
    """
    ctx = _ctx()
    await cmd_dispatch(ctx, ["25", "买资料"])
    reply = await cmd_dispatch(ctx, ["approve", "1"])
    assert "权限" in reply or "无权" in reply or "不足" in reply
    # And nothing was approved.
    assert "已批准" not in reply


async def test_admin_can_approve_someone_elses_request(cmd_dispatch):
    requester = _ctx(user_id="u1", role=Role.MEMBER)
    await cmd_dispatch(requester, ["25", "买资料"])

    # APPROVE_PAYMENT is OWNER-only by policy (money must not be admin-delegable),
    # so the second person is another owner — the operator's second account.
    approver = _ctx(user_id="boss", role=Role.OWNER)
    reply = await cmd_dispatch(approver, ["approve", "1"])
    assert "已批准" in reply
    assert "不执行任何支付" in reply, "reply must not imply the bot pays"


async def test_requester_cannot_approve_own_request_even_as_owner(cmd_dispatch):
    """Holding the permission is not the same as being allowed to use it here."""
    owner = _ctx(user_id="boss", role=Role.OWNER)
    await cmd_dispatch(owner, ["25", "买资料"])
    reply = await cmd_dispatch(owner, ["approve", "1"])
    assert "自己" in reply
    assert "已批准" not in reply


async def test_admin_cannot_approve_even_with_a_request_of_their_own(cmd_dispatch):
    """Admin is a bot-administration role; it must not carry money authority.

    If it did, every bot admin could approve spend, and the "second person" would
    just be "any admin" — which in a single-admin deployment is the requester.
    """
    await cmd_dispatch(_ctx(user_id="u1"), ["25", "买资料"])
    reply = await cmd_dispatch(_ctx(user_id="boss", role=Role.ADMIN), ["approve", "1"])
    assert "已批准" not in reply


async def test_owner_can_deny(cmd_dispatch):
    await cmd_dispatch(_ctx(user_id="u1"), ["25", "买资料"])
    reply = await cmd_dispatch(_ctx(user_id="boss", role=Role.OWNER), ["deny", "1", "不需要"])
    assert "已驳回" in reply


async def test_decision_reports_what_is_still_queued(cmd_dispatch):
    """An approver working through a queue must not have to re-list to know if they are done.

    ``render_pending_notice`` existed but had no caller — the kind of helper that makes
    the feature look finished in review while the operator still has to type
    ``/budget list`` after every decision.
    """
    await cmd_dispatch(_ctx(user_id="u1"), ["10", "第一个"])
    await cmd_dispatch(_ctx(user_id="u2"), ["10", "第二个"])

    approver = _ctx(user_id="boss", role=Role.OWNER)
    first = await cmd_dispatch(approver, ["approve", "1"])
    assert "待审批申请" in first
    assert "用 /budget list 查看" in first

    second = await cmd_dispatch(approver, ["approve", "2"])
    # Nothing left: no notice rather than "有 0 笔待审批".
    assert "待审批申请" not in second


async def test_approval_is_not_replayable_via_command(cmd_dispatch):
    await cmd_dispatch(_ctx(user_id="u1"), ["25", "买资料"])
    approver = _ctx(user_id="boss", role=Role.OWNER)
    await cmd_dispatch(approver, ["approve", "1"])
    reply = await cmd_dispatch(approver, ["approve", "1"])
    assert "已经是" in reply or "不能重复" in reply


# ------------------------------------------------------------------- scope


async def test_scope_comes_from_the_event_not_the_arguments(cmd_dispatch):
    """There is no argument that widens the scope — same rule as /recall.

    A member of group 100 cannot touch group 200's quota by naming it, because
    the scope is read from ``ctx.event.session_key`` and never from ``args``.
    """
    other_ctx = _ctx(group_id=OTHER_GROUP, user_id="x")
    await cmd_dispatch(other_ctx, ["40", "另一个群的书"])

    # Group 100 sees none of group 200's usage.
    reply = await cmd_dispatch(_ctx(user_id="u1"), [])
    assert "40.00" not in reply


async def test_request_id_from_another_group_is_not_found(cmd_dispatch):
    """Must look nonexistent, not forbidden — otherwise it is an id oracle."""
    await cmd_dispatch(_ctx(group_id=OTHER_GROUP, user_id="x"), ["40", "别的"])
    reply = await cmd_dispatch(_ctx(user_id="boss", role=Role.OWNER), ["approve", "1"])
    assert "没有编号" in reply


# ------------------------------------------------------------------ listing


async def test_list_shows_pending_for_this_group_only(cmd_dispatch):
    await cmd_dispatch(_ctx(user_id="u1"), ["10", "本群的书"])
    await cmd_dispatch(_ctx(group_id=OTHER_GROUP, user_id="x"), ["20", "别群的"])
    reply = await cmd_dispatch(_ctx(user_id="u1"), ["list"])
    assert "10.00" in reply
    assert "20.00" not in reply


async def test_cancel_only_works_for_the_requester(cmd_dispatch):
    await cmd_dispatch(_ctx(user_id="u1"), ["10", "书"])
    reply = await cmd_dispatch(_ctx(user_id="u2"), ["cancel", "1"])
    assert "没有编号" in reply

    reply = await cmd_dispatch(_ctx(user_id="u1"), ["cancel", "1"])
    assert "已撤回" in reply


@pytest.fixture
def cmd_dispatch(cmds):
    """Bind the handler with a stable pending-request id space per test."""

    async def _call(ctx, args):
        return await cmds.handle(ctx, args)

    return _call
