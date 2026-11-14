"""Control kill switch: one file that stops the bot's screen/control operations.

Why a file, and why read fresh on every call: the design's kill switch must be
something the *operator* holds, not something the runtime can talk itself out of.
A file under ``data/`` is state outside the process — patching in-memory flags,
re-reading env, or re-enabling from a chat command cannot remove it. Only deleting
the file revives operations, and deletion exists in exactly two places: the
owner-only API (token credential required) and the operator's own hands on the
filesystem. Plugins and the model have neither.

This gate currently covers the screen capability (phase 1). When the control
plane (input injection) is built, its module MUST consult the same file — that is
a hard precondition written into ``docs/autonomous-capabilities-design.md`` §1.5,
not a convention.

Fail-closed everywhere: a corrupt or unreadable switch file still counts as
"killed" — the operator pressed the button; the least useful response is to
forget it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from soapbot.security.files import write_private_file

KILL_FILENAME = "control_kill.switch"


def kill_file(settings: Any) -> Path:
    """Where the switch lives, derived from settings so tests can sandbox it."""
    data_dir = Path(getattr(settings, "data_dir", "data"))
    return data_dir / KILL_FILENAME


def is_killed(settings: Any) -> dict[str, Any] | None:
    """The switch's content when engaged, else ``None``. Read fresh per call.

    A corrupt file is still "killed": the operator wrote something here on
    purpose, and a parse failure must not silently re-arm the machine.
    """
    path = kill_file(settings)
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        content = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"reason": "control_killed", "corrupt": True}
    return content if isinstance(content, dict) else {"reason": "control_killed", "corrupt": True}


def engage(settings: Any, *, reason: str, by: str) -> dict[str, Any]:
    """Engage the switch. Callable from the owner API and the ``/panic`` command."""
    content = {"reason": reason or "operator", "by": by, "ts": time.time()}
    write_private_file(kill_file(settings), json.dumps(content).encode("utf-8"), what="control kill switch")
    return content


def revive(settings: Any) -> None:
    """Disengage. Deliberately reachable ONLY from the owner API and the operator's
    own hands: there is no command, surface or model-callable path that imports
    this — an engaged switch survives a compromised chat, by construction."""
    kill_file(settings).unlink(missing_ok=True)
