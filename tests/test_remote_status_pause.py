"""Remote configuration from the weak ends — the conservative half (audit-adjacent item).

What this batch deliberately is **not**: a way to edit providers, adapters or secrets from
QQ. Those stay behind the panel's OWNER + approval flow, because the whole security model
is that a weak end (QQ / web / app) must not be able to reach strong-end execution. What
it *is*: two read-mostly operations an operator genuinely needs from a phone — "is it
alive, and what is it doing" and "stop talking for a moment" — with no configuration
surface, no credentials, and nothing that survives a restart.

Pinned here:

* ``/status`` answers with version / uptime / pause state and **nothing** about the
  deployment (no provider, host, path);
* ``/pause`` stops ordinary replies but **not commands**, or ``/resume`` could only be
  issued from the desktop end;
* archiving continues while paused — the record of what people said is not the
  operator's to suppress;
* pause is ADMIN, and a restart clears it (fail-safe: a pause must never be a lockout).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import soapbot.core.pause as pause  # dotted path: check_test_gaps counts references by it
from soapbot.core.message import (
    IncomingMessage,
    MessageScene,
    MessageSegment,
    SegmentType,
    Sender,
)
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import SkipReplyStage, _command_text
from soapbot.memory.stages import CommandStage
from soapbot.security.principal import Role


@pytest.fixture(autouse=True)
def _clean_pause():
    pause.reset_for_tests()
    yield
    pause.reset_for_tests()


def _event(text: str) -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id="1",
        scene=MessageScene.GROUP,
        group_id="1",
        sender=Sender(user_id="42", nickname="小明"),
        segments=[MessageSegment.text(text)],
    )


def _ctx(text: str) -> PipelineContext:
    ctx = PipelineContext(event=_event(text), adapter=object())
    ctx.extras["replies_here"] = True
    return ctx


# ------------------------------------------------------------------ the gate itself


async def test_pause_stops_ordinary_messages() -> None:
    pause.pause(actor="tester")
    result = await SkipReplyStage().run(_ctx("你好呀"))
    assert result.halt is True
    assert result.reason == "paused"
    assert pause.suppressed == 1


@pytest.mark.parametrize("text", ["/resume", "!resume", "／resume", "  !status"])
async def test_pause_never_swallows_commands(text: str) -> None:
    """Or ``/resume`` could only be pressed on the desktop end."""
    pause.pause(actor="tester")
    result = await SkipReplyStage().run(_ctx(text))
    assert result.halt is False, f"{text!r} was swallowed by the pause"
    assert pause.suppressed == 0


def _group_mention_ctx(text: str) -> PipelineContext:
    """A real group message: the bot is @-mentioned, so the AT segment comes first.

    ``event.text`` renders that AT as ``"@2268360864"``; ``CommandStage`` joins only
    TEXT segments. The pause gate used the rendered form, which is how ``/resume`` came
    to do nothing while ``/pause`` (issued unpaused) had worked.
    """
    event = IncomingMessage(
        adapter="onebot11",
        message_id="2",
        scene=MessageScene.GROUP,
        group_id="1",
        self_id="2268360864",
        sender=Sender(user_id="2191659120", nickname="运营"),
        segments=[
            MessageSegment(type=SegmentType.AT, data={"qq": "2268360864"}),
            MessageSegment.text(" " + text),
        ],
    )
    ctx = PipelineContext(event=event, adapter=object())
    ctx.extras["replies_here"] = True
    return ctx


async def test_a_paused_group_command_still_gets_through_the_mention() -> None:
    """Measured on the deployed bot: /pause took effect, /resume silently did nothing."""
    pause.pause(actor="tester")
    ctx = _group_mention_ctx("/resume")
    assert ctx.event.text.startswith("@"), "fixture must reproduce the @-prefixed form"

    result = await SkipReplyStage().run(ctx)

    assert result.halt is False, "/resume must survive the pause gate in a group"
    assert pause.suppressed == 0
    # It is also the same text the command stage acts on.
    assert ctx.event.text == "@2268360864 /resume"
    assert _command_text(ctx) == "/resume"


async def test_a_paused_group_message_without_a_command_is_still_suppressed() -> None:
    """The fix must not turn the pause off for group chatter."""
    pause.pause(actor="tester")
    result = await SkipReplyStage().run(_group_mention_ctx("在吗"))
    assert result.halt is True
    assert result.reason == "paused"
    assert pause.suppressed == 1


async def test_not_paused_means_no_change() -> None:
    result = await SkipReplyStage().run(_ctx("随便说说"))
    assert result.halt is False


# ------------------------------------------------------------------------ /pause + /resume


def test_pause_and_resume_permissions() -> None:
    from soapbot.security.principal import PERMISSION_MIN_ROLE

    for command in ("pause", "resume"):
        permission = CommandStage.COMMAND_PERMISSIONS[command]
        assert PERMISSION_MIN_ROLE[permission] is Role.ADMIN, command
    status_permission = CommandStage.COMMAND_PERMISSIONS["status"]
    # Same floor as /ping: version + uptime + pause state is not privileged, and a
    # guest being able to ask "are you alive" is the point of a status command.
    assert PERMISSION_MIN_ROLE[status_permission] is Role.GUEST


async def test_pause_reports_who_and_is_idempotent() -> None:
    stage = CommandStage(store=None, kb=None)
    ctx = _ctx("/pause")
    ctx.extras["principal"] = _principal(Role.ADMIN)
    first = await stage._cmd_pause(ctx, [])
    assert "已暂停回复" in first
    second = await stage._cmd_pause(ctx, [])
    assert "已经在暂停中" in second
    assert pause.is_paused() is True


async def test_resume_is_idempotent_and_names_the_previous_actor() -> None:
    stage = CommandStage(store=None, kb=None)
    pause.pause(actor="前任管理员")
    ctx = _ctx("/resume")
    ctx.extras["principal"] = _principal(Role.ADMIN)
    reply = await stage._cmd_resume(ctx, [])
    assert "已恢复回复" in reply and "前任管理员" in reply
    assert pause.is_paused() is False
    assert "当前没有暂停" in await stage._cmd_resume(ctx, [])


async def test_a_restart_clears_the_pause() -> None:
    """Fail-safe: a paused bot must never require the desktop end to un-stick it."""
    pause.pause(actor="tester")
    assert pause.is_paused() is True
    pause.reset_for_tests()  # what a fresh process looks like
    assert pause.is_paused() is False


# ---------------------------------------------------------------------------- /status


async def test_status_reports_only_non_sensitive_facts() -> None:
    from soapbot import __version__

    stage = CommandStage(store=None, kb=None)
    ctx = _ctx("/status")
    ctx.extras["principal"] = _principal(Role.MEMBER)
    reply = await stage._cmd_status(ctx, [])
    assert __version__ in reply
    assert "运行时长" in reply
    assert "运行中" in reply
    # Nothing about the deployment: no provider, host, path, or key material.
    lowered = reply.lower()
    for forbidden in ("http://", "https://", "/data", "provider", "api", "token", "host"):
        assert forbidden not in lowered, f"status leaked {forbidden!r}"


async def test_status_shows_the_pause_and_its_cost() -> None:
    stage = CommandStage(store=None, kb=None)
    ctx = _ctx("/status")
    ctx.extras["principal"] = _principal(Role.MEMBER)
    pause.pause(actor="管理员")
    pause.note_suppressed()
    reply = await stage._cmd_status(ctx, [])
    assert "已暂停" in reply
    assert "1 条消息" in reply


def _principal(role: Role):
    from soapbot.security.principal import Principal

    return Principal(
        user_id="1", display_name="操作者", role=role,
        scene="group", group_id="1", authenticated=True,
    )
