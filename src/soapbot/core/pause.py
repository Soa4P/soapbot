"""Process-wide reply pause — the conservative half of remote operation from QQ.

Why a module and not a field on ``BotRuntime``
---------------------------------------------
The command handler and the dispatch path live in different objects (``CommandStage``
does not receive the runtime), and threading a reference through the whole pipeline for
one boolean is more coupling than the feature is worth. A module-level flag is also the
right *lifetime*: a pause must not survive a restart. If it did, a single ``/pause`` from
a compromised weak end (or a mistake) would leave the bot deaf until someone opened the
panel — the opposite of a safe default for a stop button.

What it does and does not stop
------------------------------
Paused means "do not answer ordinary messages". Commands still run, because ``/resume``
is itself a command — a pause that also swallowed commands would be a one-way switch
operable only from the desktop end, which is exactly the cross-end asymmetry this
project avoids. Archiving continues too: the record of what people said is not the
operator's to suppress.

Every transition is audited, because "the bot stopped answering" is the kind of event an
operator later needs to attribute to a person and a time.
"""

from __future__ import annotations

import time

#: Monotonic start of this process, so ``/status`` can report uptime without a clock.
STARTED_AT = time.monotonic()

_paused = False
#: Who paused, for the audit line and the status answer. Never a credential.
_paused_by = ""
_paused_at = 0.0
#: Messages dropped while paused, so an operator can see what a pause actually cost.
suppressed = 0


def is_paused() -> bool:
    return _paused


def pause(*, actor: str = "") -> tuple[bool, str]:
    """Pause replies. Returns ``(changed, previous_actor)``."""
    global _paused, _paused_by, _paused_at
    previous = _paused_by
    if _paused:
        return False, previous
    _paused = True
    _paused_by = actor
    _paused_at = time.time()
    return True, previous


def resume(*, actor: str = "") -> tuple[bool, str]:
    """Resume replies. Returns ``(changed, previous_actor)``."""
    global _paused, _paused_by, _paused_at
    previous = _paused_by
    if not _paused:
        return False, previous
    _paused = False
    _paused_by = actor
    _paused_at = time.time()
    return True, previous


def note_suppressed() -> None:
    global suppressed
    suppressed += 1


def reset_for_tests() -> None:
    global _paused, _paused_by, _paused_at, suppressed, STARTED_AT
    _paused = False
    _paused_by = ""
    _paused_at = 0.0
    suppressed = 0
    STARTED_AT = time.monotonic()


def status_line() -> str:
    """One line for ``/status``: the pause is the only mutable part."""
    if not _paused:
        return "运行中"
    who = _paused_by or "未记录"
    when = time.strftime("%m-%d %H:%M", time.localtime(_paused_at)) if _paused_at else "?"
    return f"已暂停（{who}，{when} 起），期间已跳过 {suppressed} 条消息"
