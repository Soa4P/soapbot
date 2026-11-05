"""Collect scope and reply scope are separate decisions.

Archiving used to sit behind the wake check, so a group message nobody @-ed was never
stored. That made "remember this group" unconfigurable: the bot only kept what it was
asked about. These tests pin the two lists and the stage that stops an archive-only turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from soapbot.core.builder import build_access_policy
from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import AccessPolicy, SkipReplyStage, WhitelistStage
from soapbot.memory.stages import PersistStage


def _policy(
    reply: set[str] | None = None, collect: set[str] | None = None
) -> AccessPolicy:
    return AccessPolicy(
        group_allowlist=reply or set(),
        memory_collect_groups=collect or set(),
    )


# ------------------------------------------------------------------ admission


def test_both_lists_empty_means_fully_open() -> None:
    policy = _policy()
    for gid in ("111", "222"):
        assert policy.allows(MessageScene.GROUP, gid, "9")[0] is True
        assert policy.replies_in(gid) is True
        assert policy.collects_from(MessageScene.GROUP, gid) is True


def test_a_collected_only_group_is_admitted_but_not_replied_to() -> None:
    """The whole point of the split: learn here, stay quiet here."""
    policy = _policy(reply={"111"}, collect={"222"})

    assert policy.allows(MessageScene.GROUP, "222", "9")[0] is True, (
        "a collected group must be admitted or its history never reaches persist"
    )
    assert policy.replies_in("222") is False
    assert policy.collects_from(MessageScene.GROUP, "222") is True


def test_a_reply_only_group_is_not_archived() -> None:
    policy = _policy(reply={"111"}, collect={"222"})

    assert policy.allows(MessageScene.GROUP, "111", "9")[0] is True
    assert policy.replies_in("111") is True
    assert policy.collects_from(MessageScene.GROUP, "111") is False


def test_a_group_in_neither_scope_is_refused_outright() -> None:
    policy = _policy(reply={"111"}, collect={"222"})
    ok, reason = policy.allows(MessageScene.GROUP, "333", "9")
    assert ok is False
    assert reason == "group_not_allowed"


def test_an_empty_collect_list_means_every_group() -> None:
    """Both lists read the same way: empty = everywhere.

    An earlier version made an empty collect list inherit the reply list, so narrowing
    replies silently stopped archiving — a side effect invisible in the panel. Each list
    now stands on its own, and "empty = all" is the only rule to remember.
    """
    policy = _policy(reply={"111"})

    assert policy.collects_from(MessageScene.GROUP, "111") is True
    assert policy.collects_from(MessageScene.GROUP, "222") is True


def test_private_messages_are_always_collected() -> None:
    policy = _policy(reply={"111"}, collect={"222"})
    assert policy.collects_from(MessageScene.PRIVATE, "") is True


def test_blacklist_wins_over_both_scopes() -> None:
    policy = AccessPolicy(
        group_allowlist={"111"},
        memory_collect_groups={"111"},
        group_blacklist={"111"},
    )
    ok, reason = policy.allows(MessageScene.GROUP, "111", "9")
    assert ok is False
    assert reason == "group_blacklisted"


# ------------------------------------------------------------------ config wiring


@dataclass
class _Cfg:
    reply_groups: list[str]
    memory_collect_groups: list[str]
    group_allowlist: list[str] = None  # type: ignore[assignment]
    group_blacklist: list[str] = None  # type: ignore[assignment]
    user_blacklist: list[str] = None  # type: ignore[assignment]
    private_allowlist: list[str] = None  # type: ignore[assignment]
    allow_unknown_private: bool = False


def test_the_old_group_allowlist_still_works_as_the_reply_set() -> None:
    cfg = _Cfg(reply_groups=[], memory_collect_groups=[], group_allowlist=["111"])
    policy = build_access_policy(cfg)

    assert policy.replies_in("111") is True
    assert policy.replies_in("222") is False


def test_the_new_key_wins_when_both_are_set() -> None:
    cfg = _Cfg(
        reply_groups=["222"],
        memory_collect_groups=[],
        group_allowlist=["111"],
    )
    policy = build_access_policy(cfg)

    assert policy.replies_in("222") is True
    assert policy.replies_in("111") is False


def test_a_stand_in_config_without_the_new_fields_does_not_crash() -> None:
    """Embedders and old tests pass small objects; a missing field means 'unset'."""

    class _Old:
        group_allowlist: ClassVar[list[str]] = ["111"]
        group_blacklist: ClassVar[list[str]] = []
        user_blacklist: ClassVar[list[str]] = []
        private_allowlist: ClassVar[list[str]] = []
        allow_unknown_private: ClassVar[bool] = False

    policy = build_access_policy(_Old())
    assert policy.replies_in("111") is True


# ------------------------------------------------------------------ stages


class _Store:
    def __init__(self) -> None:
        self.archived: list[dict[str, Any]] = []

    async def archive_message(self, **kwargs: Any) -> None:
        self.archived.append(kwargs)


class _Adapter:
    """Just enough adapter for the context; these stages never touch it."""

    meta = None
    capabilities: frozenset = frozenset()


def _ctx(*, collect: bool | None, segments: list[MessageSegment] | None = None) -> PipelineContext:
    event = IncomingMessage(
        adapter="mock",
        self_id="10000",
        scene=MessageScene.GROUP,
        group_id="111",
        sender=Sender(user_id="42", nickname="tester"),
        segments=segments or [MessageSegment.text("just chatting")],
        message_id="m1",
    )
    ctx = PipelineContext(event=event, adapter=_Adapter())  # type: ignore[arg-type]
    if collect is not None:
        ctx.extras["memory_collect"] = collect
    return ctx


@pytest.mark.asyncio
async def test_persist_skips_a_group_outside_the_collect_scope() -> None:
    store = _Store()
    stage = PersistStage(store)  # type: ignore[arg-type]

    ctx = _ctx(collect=False)
    await stage.run(ctx)

    assert store.archived == []
    assert ctx.extras.get("persist_skipped") == "group_not_collected"


@pytest.mark.asyncio
async def test_persist_writes_inside_the_collect_scope() -> None:
    store = _Store()
    stage = PersistStage(store)  # type: ignore[arg-type]

    await stage.run(_ctx(collect=True))

    assert len(store.archived) == 1
    assert store.archived[0]["content"] == "just chatting"


@pytest.mark.asyncio
async def test_an_unmentioned_message_is_archived_then_stopped() -> None:
    """Order matters: the archive must happen, the turn must not continue."""
    store = _Store()
    ctx = _ctx(collect=True)
    ctx.extras["skip_reply"] = True

    await PersistStage(store).run(ctx)  # type: ignore[arg-type]
    result = await SkipReplyStage().run(ctx)

    assert len(store.archived) == 1, "an un-mentioned collected message is still history"
    assert result.halt is True
    assert result.reason == "not_woken"


@pytest.mark.asyncio
async def test_skip_reply_lets_woken_messages_through() -> None:
    ctx = _ctx(collect=True)
    ctx.extras["wake_reason"] = "at"

    assert (await SkipReplyStage().run(ctx)).halt is False


@pytest.mark.asyncio
async def test_a_collected_only_group_is_archived_but_not_answered() -> None:
    """The reply list has to gate delivery, not just admission.

    Without this, ``REPLY_GROUPS`` only decided *whether a message enters* the pipeline:
    a group that was collected but not listed for replies still answered anyone who
    @-ed the bot, which is the opposite of "stay quiet here".
    """
    store = _Store()
    ctx = _ctx(collect=True)
    ctx.extras["wake_reason"] = "at"
    ctx.extras["replies_here"] = False

    await PersistStage(store).run(ctx)  # type: ignore[arg-type]
    result = await SkipReplyStage().run(ctx)

    assert len(store.archived) == 1, "the message is still history"
    assert result.halt is True
    assert result.reason == "group_not_replied"


@pytest.mark.asyncio
async def test_whitelist_records_the_reply_decision_for_later_stages() -> None:
    """``SkipReplyStage`` reads this key; nothing else re-derives it."""
    policy = _policy(reply={"111"}, collect={"222"})

    ctx = _ctx(collect=None)
    ctx.event.group_id = "222"
    await WhitelistStage(policy).run(ctx)
    assert ctx.extras["replies_here"] is False
    assert ctx.extras["memory_collect"] is True

    ctx = _ctx(collect=None)
    ctx.event.group_id = "111"
    await WhitelistStage(policy).run(ctx)
    assert ctx.extras["replies_here"] is True
    assert ctx.extras["memory_collect"] is False


@pytest.mark.asyncio
async def test_a_missing_reply_decision_does_not_mute_the_group() -> None:
    """A stand-in context that never ran ``WhitelistStage`` must still be answered.

    Treating "key absent" as "do not reply" would silently mute every group for any
    embedder that assembles its own pipeline.
    """
    ctx = _ctx(collect=True)
    assert "replies_here" not in ctx.extras
    assert (await SkipReplyStage().run(ctx)).halt is False
