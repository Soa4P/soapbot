"""Dedup is scoped to one adapter+account, and it runs after identity is established.

Two failures motivated these cases:

* the key was the raw protocol message id. The same id is handed to every bot in the
  group, so the second bot's copy was dropped as "duplicate" even though it was the
  first time *that* bot had seen it;
* dedup ran before ``guard``. An event from an unknown peer was refused by guard but had
  already occupied the slot, so a later legitimate copy of the same id was discarded —
  the message was never processed and never looked like an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.core.message import IncomingMessage, MessageScene, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import DedupStage

ROOT = Path(__file__).resolve().parents[1]


def _ctx(
    *, adapter: str = "onebot11", self_id: str = "1001", message_id: str = "42"
) -> PipelineContext:
    event = IncomingMessage(
        adapter=adapter,
        message_id=message_id,
        scene=MessageScene.GROUP,
        sender=Sender(user_id="9001"),
        segments=[],
        self_id=self_id,
    )
    return PipelineContext(event=event, adapter=None)


@pytest.mark.asyncio
async def test_the_same_id_from_two_accounts_is_not_a_duplicate() -> None:
    stage = DedupStage()

    assert (await stage.run(_ctx(self_id="1001"))).halt is False
    assert (await stage.run(_ctx(self_id="2002"))).halt is False, (
        "a different account's id was dropped as a duplicate"
    )
    # A real replay from the same account is still refused.
    assert (await stage.run(_ctx(self_id="1001"))).halt is True


def test_guard_runs_before_dedup() -> None:
    source = (ROOT / "src" / "soapbot" / "core" / "builder.py").read_text(encoding="utf-8")
    guard = source.index("GuardStage(")
    dedup = source.index("DedupStage()")
    assert guard < dedup, (
        "dedup moved back in front of guard, so rejected events consume dedup slots "
        "and a later legitimate copy of the same id is lost"
    )
