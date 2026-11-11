"""Read-mostly chat archive API for the web and mobile clients.

Semantics that must not drift:

* QQ is the source of truth. Nothing in this module calls an adapter.
* A note is a row with ``role="note"`` and ``adapter="web"``; it is visible to the
  account that wrote it only through the same archive, and is never delivered.
* Isolation is server-side: a member sees a session only if a membership row exists.
  Filtering in the browser would be a suggestion, not a boundary.
* ``/stream`` is SSE backed by a 1.5 s cursor poll. It is not a message bus, and the
  documentation says so rather than implying push.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from soapbot.accounts import Account, has_access, list_memberships
from soapbot.accounts.service import active_account_from_claims
from soapbot.api.auth import require_api_auth
from soapbot.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

STREAM_INTERVAL_SECONDS = 1.5
MAX_NOTE_LENGTH = 4000


def surfaces() -> dict[str, bool]:
    """Which chat clients are switched on.

    Read from ``Settings`` rather than ``os.environ``: ``.env`` is consumed by
    pydantic-settings and never exported into the process environment, so an
    ``os.getenv`` check would silently ignore the file the operator actually edits.
    Read per call, so a test (or a future reload endpoint) can flip a flag without
    re-importing the module.
    """
    return {
        "web": bool(getattr(settings, "chat_web_enabled", True)),
        "app": bool(getattr(settings, "chat_app_enabled", False)),
        "desktop": bool(getattr(settings, "chat_desktop_enabled", False)),
    }


def _ensure_surface() -> None:
    if not any(surfaces().values()):
        # 404, not 403: with every client switched off the endpoint should look like
        # it is not part of this deployment.
        raise HTTPException(status_code=404, detail="chat surfaces are disabled")


def _memory(request: Request):
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None or getattr(runtime, "memory", None) is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime.memory


@router.get("/surfaces")
async def chat_surfaces() -> dict[str, bool]:
    """Client switches, readable without a token so a login page can hide itself."""
    return surfaces()


async def _account(request: Request, auth: dict[str, Any]) -> Account:
    _ensure_surface()
    memory = _memory(request)
    account = await active_account_from_claims(memory.db, auth)
    if account is None:
        # Same answer for "deleted" and "disabled": the caller learns only that this
        # credential is not a way in any more.
        raise HTTPException(status_code=401, detail="account no longer exists")
    if account.id == 0:
        # The bootstrap token resolves to a synthetic owner. It exists to create the
        # first account, and it must not double as a read key for the whole archive:
        # otherwise the one credential printed at setup is also the widest one.
        raise HTTPException(status_code=401, detail="sign in with an account to read the archive")
    return account


async def _require_session(request: Request, account: Account, session_key: str) -> None:
    if not await has_access(_memory(request).db, account, session_key):
        # 404 rather than 403: confirming that a session exists is itself information
        # about conversations the caller was not invited to.
        raise HTTPException(status_code=404, detail="session not found")


@router.get("/sessions")
async def sessions(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    memory = _memory(request)
    account = await _account(request, auth)
    if account.is_owner:
        rows = await memory.list_sessions(limit=200)
    else:
        rows = await memory.list_sessions(
            limit=200, session_keys=await list_memberships(memory.db, account.id)
        )
    return {"sessions": rows, "scope": "all" if account.is_owner else "member"}


@router.get("/messages")
async def messages(
    request: Request,
    session_key: str = Query(..., min_length=1, max_length=128),
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    memory = _memory(request)
    account = await _account(request, auth)
    await _require_session(request, account, session_key)
    rows = await memory.messages_since(session_key, after_id=after_id, limit=limit)
    return {
        "session_key": session_key,
        "messages": rows,
        "next_after_id": rows[-1]["id"] if rows else after_id,
    }


class NoteRequest(BaseModel):
    session_key: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=MAX_NOTE_LENGTH)


@router.post("/notes")
async def add_note(
    payload: NoteRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    memory = _memory(request)
    account = await _account(request, auth)
    await _require_session(request, account, payload.session_key)
    try:
        note = await memory.add_note(
            session_key=payload.session_key,
            content=payload.content,
            user_id=f"web:{account.id}",
            user_name=account.username,
        )
    except ValueError:
        # The store's message names internal bounds; a client only needs to know the
        # note was refused. The detail stays in the server log.
        logger.warning(
            "note rejected session=%s account=%s", payload.session_key, account.id, exc_info=True
        )
        raise HTTPException(status_code=400, detail="note content is empty or too long") from None
    logger.info(
        "note archived account=%s session=%s chars=%d",
        account.username,
        payload.session_key,
        len(payload.content),
    )
    return {"note": note, "delivered": False}


async def event_stream(memory, request: Request, session_key: str, after_id: int):
    """Yield SSE frames from a cursor. A plain async generator, so it is testable."""
    cursor = after_id
    while True:
        if await request.is_disconnected():
            break
        rows = await memory.messages_since(session_key, after_id=cursor, limit=100)
        for row in rows:
            cursor = row["id"]
            yield f"data: {json.dumps(row, ensure_ascii=False)}\n\n"
        if not rows:
            # Keep-alive comment: proxies drop idle connections, and a dropped
            # stream looks like "no new messages" to the client.
            yield ": keep-alive\n\n"
        await asyncio.sleep(STREAM_INTERVAL_SECONDS)


@router.get("/stream")
async def stream(
    request: Request,
    session_key: str = Query(..., min_length=1, max_length=128),
    after_id: int = Query(0, ge=0),
    auth: dict[str, Any] = Depends(require_api_auth),
) -> StreamingResponse:
    memory = _memory(request)
    account = await _account(request, auth)
    await _require_session(request, account, session_key)
    return StreamingResponse(
        event_stream(memory, request, session_key, after_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
