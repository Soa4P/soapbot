"""Unified-chat session mapping: a bound QQ user joins the account's web session.

Why a mapper and not adapter-side rewriting: the mapping depends on the accounts
database and the operator's binding decisions, which adapters must not know about.
``BotRuntime.dispatch`` calls the mapper *before* taking the session lock — the key
may change, so locking the derived ``qq:private:<uin>`` key would guard a session
nobody uses. A miss leaves the event untouched: without a binding (or with the flag
off) the derived key is used exactly as before, so the default deployment's behavior
is byte-for-byte unchanged.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from soapbot.accounts.service import account_by_qq_user
from soapbot.config import settings
from soapbot.core.message import IncomingMessage, MessageScene

#: How long a resolved (or negative) binding lookup stays cached. Bindings change
#: rarely; the TTL bounds how long an unbind takes to take effect.
_TTL_SECONDS = 30.0
_MAX_ENTRIES = 512


class SessionMapper:
    """Map ``qq:private:<uin>`` events onto ``web:private:account-<id>`` sessions."""

    def __init__(self, db: Any, *, ttl: float = _TTL_SECONDS, max_entries: int = _MAX_ENTRIES):
        self._db = db
        self._ttl = ttl
        self._max = max_entries
        self._cache: dict[str, tuple[str, float]] = {}
        """``qq_user_id -> (account_id or "", expiry)`` — empty string caches a miss."""
        self._lock = threading.Lock()

    async def __call__(self, event: IncomingMessage) -> str | None:
        """Return the unified session key, or ``None`` to leave the event alone."""
        if not getattr(settings, "chat_unified_enabled", False):
            return None
        if event.scene is not MessageScene.PRIVATE or event.adapter != "onebot11":
            return None
        qq_id = str(event.sender.user_id or "").strip()
        if not qq_id:
            return None
        cached = self._peek(qq_id, time.time())
        if cached is not None:
            account_id = cached
        else:
            account = await account_by_qq_user(self._db, qq_id)
            account_id = str(account.id) if account is not None else ""
            self._put(qq_id, account_id, time.time())
        if not account_id:
            return None
        return f"web:private:account-{account_id}"

    # ------------------------------------------------------------------ cache
    def _peek(self, qq_id: str, now: float) -> str | None:
        with self._lock:
            entry = self._cache.get(qq_id)
            if entry is None or entry[1] <= now:
                return None
            return entry[0]

    def _put(self, qq_id: str, account_id: str, now: float) -> None:
        with self._lock:
            if len(self._cache) >= self._max and qq_id not in self._cache:
                # Drop the soonest-expiring entry; the map is bounded by design.
                oldest = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest]
            self._cache[qq_id] = (account_id, now + self._ttl)

    def invalidate(self, qq_user_id: str = "") -> None:
        """Drop one cached binding (or all). Called when the owner rebinds."""
        with self._lock:
            if qq_user_id:
                self._cache.pop(str(qq_user_id), None)
            else:
                self._cache.clear()
