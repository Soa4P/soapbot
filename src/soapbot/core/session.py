"""Per-session serialisation and multi-turn state.

Two separate concerns, deliberately split:

* ``SessionLockManager`` guarantees that messages from the same group/user are
  processed one at a time. Without this, two concurrent @mentions in the same
  group race on the conversation history and produce interleaved garbage.
* ``SessionStore`` holds short-lived plugin/session state (TTL based).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any


class SessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, session_key: str) -> asyncio.Lock:
        return self._locks[session_key]

    def is_locked(self, session_key: str) -> bool:
        lock = self._locks.get(session_key)
        return lock is not None and lock.locked()

    def active_count(self) -> int:
        return sum(1 for lock in self._locks.values() if lock.locked())


class SessionStore:
    """TTL key-value store keyed by (namespace, session_key, key)."""

    def __init__(self, default_ttl: int = 1800) -> None:
        self._data: dict[tuple[str, str, str], tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, namespace: str, session_key: str, key: str = "state") -> Any:
        entry = self._data.get((namespace, session_key, key))
        if entry is None:
            return None
        value, expires = entry
        if expires and expires < time.time():
            self._data.pop((namespace, session_key, key), None)
            return None
        return value

    def set(
        self, namespace: str, session_key: str, value: Any, key: str = "state", ttl: int | None = None
    ) -> None:
        ttl = self._default_ttl if ttl is None else ttl
        expires = time.time() + ttl if ttl > 0 else 0.0
        self._data[(namespace, session_key, key)] = (value, expires)

    def delete(self, namespace: str, session_key: str, key: str = "state") -> None:
        self._data.pop((namespace, session_key, key), None)

    def purge_expired(self) -> int:
        now = time.time()
        stale = [k for k, (_, exp) in self._data.items() if exp and exp < now]
        for k in stale:
            self._data.pop(k, None)
        return len(stale)
