"""One person must not be able to spend the operator's budget unopposed.

The existing limiters all count *refusals* — a burst of denials means enumeration. That is
a different question from cost. Nothing bounded a user who simply talks a lot: every
message is a provider call, so one enthusiastic member can spend the budget without ever
being refused anything.

The property that matters is not "a message was refused". It is "the model was not
called": a quota that fires after the provider call has already cost the money it exists
to protect.
"""

from __future__ import annotations

import pytest

from soapbot.core.pipeline import PipelineContext
from soapbot.security.principal import Permission, Principal, Role
from soapbot.security.stages import ModelQuotaStage


def _principal(user_id: str = "1001", role: Role = Role.MEMBER, adapter: str = "onebot11"):
    return Principal(
        user_id=user_id,
        role=role,
        adapter=adapter,
        scene="group",
        group_id="9000",
        source="config",
        authenticated=True,
        granted=frozenset({Permission.CHAT}),
    )


@pytest.fixture
def ctx_factory():
    def build(principal: Principal) -> PipelineContext:
        from soapbot.core.message import IncomingMessage, MessageScene, Sender

        event = IncomingMessage(
            adapter="onebot11",
            message_id="m1",
            scene=MessageScene.GROUP,
            sender=Sender(user_id=principal.user_id, nickname="tester"),
            segments=[],
            group_id="9000",
            self_id="10000",
            trace_id="t-quota",
        )
        ctx = PipelineContext(event=event, adapter=None, locale="zh")
        ctx.extras["principal"] = principal
        return ctx

    return build


@pytest.mark.asyncio
async def test_the_model_is_not_called_once_the_quota_is_spent(ctx_factory) -> None:
    stage = ModelQuotaStage(calls=2, window_seconds=60.0)
    principal = _principal()

    for _ in range(2):
        result = await stage.run(ctx_factory(principal))
        assert result.halt is False, "a turn inside the quota must proceed"

    blocked = await stage.run(ctx_factory(principal))
    assert blocked.halt is False, "the turn still needs to reach the reply stage"
    ctx = ctx_factory(principal)
    await stage.run(ctx)

    assert ctx.extras["skip_model"] is True, "the model would still have been called"
    assert ctx.extras["quota_exceeded"] is True
    assert ctx.model_reply, "the user got silence instead of an explanation"
    assert stage.status()["refused"] == 2


@pytest.mark.asyncio
async def test_the_refusal_is_audited(ctx_factory) -> None:
    """A silent block looks like a broken bot to the operator reading the log."""
    from soapbot.security.audit import get_audit_log

    stage = ModelQuotaStage(calls=1, window_seconds=60.0)
    principal = _principal(user_id="5555")
    await stage.run(ctx_factory(principal))
    await stage.run(ctx_factory(principal))

    events = [
        e
        for e in get_audit_log().recent(limit=100)
        if e.get("action") == "model_quota" and e.get("outcome") == "block"
    ]
    assert events, "the quota refusal left no audit trail"


@pytest.mark.asyncio
async def test_two_users_have_separate_budgets(ctx_factory) -> None:
    """The key must include the user, or one person's traffic throttles the group."""
    stage = ModelQuotaStage(calls=1, window_seconds=60.0)

    await stage.run(ctx_factory(_principal(user_id="1")))
    other = ctx_factory(_principal(user_id="2"))
    await stage.run(other)

    assert other.extras.get("quota_exceeded") is not True


@pytest.mark.asyncio
async def test_the_window_slides_rather_than_resetting(ctx_factory) -> None:
    """A fixed window lets a caller spend the budget twice at the seam."""
    stage = ModelQuotaStage(calls=1, window_seconds=60.0)
    principal = _principal(user_id="7777")

    await stage.run(ctx_factory(principal))
    second = ctx_factory(principal)
    await stage.run(second)
    assert second.extras.get("quota_exceeded") is True

    # Simulate the window passing by backdating the recorded hit.
    bucket = stage._limiter._hits["onebot11:7777"]
    bucket[0] -= 61.0

    third = ctx_factory(principal)
    await stage.run(third)
    assert third.extras.get("quota_exceeded") is not True


@pytest.mark.asyncio
async def test_a_privileged_user_is_exempt(ctx_factory) -> None:
    """An operator debugging the bot must not be throttled by the control they operate."""
    stage = ModelQuotaStage(calls=1, window_seconds=60.0)
    admin = _principal(user_id="1", role=Role.ADMIN)

    for _ in range(5):
        ctx = ctx_factory(admin)
        await stage.run(ctx)
        assert ctx.extras.get("quota_exceeded") is not True


@pytest.mark.asyncio
async def test_a_turn_without_a_principal_is_not_refused(ctx_factory) -> None:
    """The quota is a cost control, not an authorization gate; Guard owns that case."""
    stage = ModelQuotaStage(calls=1, window_seconds=60.0)
    ctx = ctx_factory(_principal())
    ctx.extras.pop("principal")

    result = await stage.run(ctx)
    assert result.halt is False
