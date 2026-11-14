"""Operator-facing screen safety API: the kill switch and the operation log.

Owner + token credential only (the same bar as budget decisions): engaging the
switch from a loopback read or a stolen cookie would be meaningless, and the ops
log is exactly the "what did the bot do on that machine" view the design requires
the operator to have — it must not be readable by the chat participants it
describes operations about.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from soapbot.api.auth import require_role
from soapbot.config import settings
from soapbot.security.principal import Role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/screen", tags=["screen"])

auth = Depends(require_role(Role.OWNER, require_credential=True))


class KillRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=200)


@router.get("/ops")
async def ops(limit: int = 100, auth_dep: dict[str, Any] = auth) -> dict[str, Any]:
    """The operator's live view: switch state plus the operation ring.

    Metadata only by construction — the ring never receives frame content (pinned
    by tests, same zero-leak rule as the audit).
    """
    from soapbot.screen.kill import is_killed
    from soapbot.screen.opslog import SCREEN_OPS

    return {
        "killed": is_killed(settings) is not None,
        "kill": is_killed(settings),
        "ops": SCREEN_OPS.recent(limit),
    }


@router.post("/kill")
async def engage_kill(payload: KillRequest, auth_dep: dict[str, Any] = auth) -> dict[str, Any]:
    """Engage the control kill switch. Takes effect on the very next capture
    attempt — the gate reads the file fresh per call, so there is no cache window."""
    from soapbot.screen.kill import engage, is_killed
    from soapbot.screen.opslog import SCREEN_OPS

    by = str((auth_dep or {}).get("subject") or "owner")
    content = engage(settings, reason=payload.reason, by=by)
    SCREEN_OPS.record(action="screen.kill", outcome="allow", reason=payload.reason, by=by)
    logger.warning("control kill switch engaged by=%s reason=%s", by, payload.reason)
    return {"ok": True, "kill": content, "killed": is_killed(settings) is not None}


@router.delete("/kill")
async def revive_control(auth_dep: dict[str, Any] = auth) -> dict[str, Any]:
    """Disengage. Owner + token credential only; no command or plugin path leads
    here — that asymmetry is the point (see screen/kill.py)."""
    from soapbot.screen.kill import is_killed, revive
    from soapbot.screen.opslog import SCREEN_OPS

    by = str((auth_dep or {}).get("subject") or "owner")
    revive(settings)
    SCREEN_OPS.record(action="screen.revive", outcome="allow", by=by)
    logger.warning("control kill switch disengaged by=%s", by)
    return {"ok": True, "killed": is_killed(settings) is not None}
