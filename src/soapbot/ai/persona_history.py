"""Immutable persona versions.

Growth writes take effect immediately, so the only way back from a bad write is a
row that predates it. Rows are append-only: a rollback produces a *new* version
instead of deleting history, which is what makes "roll back the rollback" work.

Storage is a separate SQLite file rather than the main database because a persona
file can be corrupted by hand, and a broken card must not be able to prevent the
version log from opening.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS persona_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    source_session TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'model',
    flagged INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    UNIQUE (persona_id, version)
);
CREATE INDEX IF NOT EXISTS idx_persona_versions
    ON persona_versions (persona_id, version DESC);
"""


@dataclass(slots=True)
class PersonaVersion:
    persona_id: str
    version: int
    payload: dict[str, Any]
    content: str
    source_session: str
    trace_id: str
    actor: str
    flagged: bool
    created_at: float


class PersonaHistory:
    """Append-only version log for persona cards."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # ---------------------------------------------------------------- plumbing
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        return conn

    @staticmethod
    def _row(row: sqlite3.Row) -> PersonaVersion:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = {}
        return PersonaVersion(
            persona_id=row["persona_id"],
            version=int(row["version"]),
            payload=payload if isinstance(payload, dict) else {},
            content=row["content"] or "",
            source_session=row["source_session"] or "",
            trace_id=row["trace_id"] or "",
            actor=row["actor"] or "model",
            flagged=bool(row["flagged"]),
            created_at=float(row["created_at"]),
        )

    # ---------------------------------------------------------------- writes
    def append(
        self,
        *,
        persona_id: str,
        payload: dict[str, Any],
        content: str = "",
        source_session: str = "",
        trace_id: str = "",
        actor: str = "model",
        flagged: bool = False,
    ) -> PersonaVersion:
        """Store one version and return it.

        The version number is allocated here, inside the same transaction as the
        insert, so two concurrent growth writes cannot both claim ``n+1``.
        """
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM persona_versions "
                    "WHERE persona_id = ?",
                    (persona_id,),
                ).fetchone()
                version = int(row[0])
                created = time.time()
                conn.execute(
                    "INSERT INTO persona_versions "
                    "(persona_id, version, payload, content, source_session, trace_id,"
                    " actor, flagged, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        persona_id,
                        version,
                        body,
                        content,
                        source_session,
                        trace_id,
                        actor,
                        1 if flagged else 0,
                        created,
                    ),
                )
        finally:
            conn.close()
        return PersonaVersion(
            persona_id=persona_id,
            version=version,
            payload=dict(payload),
            content=content,
            source_session=source_session,
            trace_id=trace_id,
            actor=actor,
            flagged=flagged,
            created_at=created,
        )

    # ---------------------------------------------------------------- reads
    def list_versions(self, persona_id: str, *, limit: int = 50) -> list[PersonaVersion]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM persona_versions WHERE persona_id = ? "
                "ORDER BY version DESC LIMIT ?",
                (persona_id, max(1, min(limit, 200))),
            ).fetchall()
        finally:
            conn.close()
        return [self._row(row) for row in rows]

    def get(self, persona_id: str, version: int) -> PersonaVersion | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM persona_versions WHERE persona_id = ? AND version = ?",
                (persona_id, version),
            ).fetchone()
        finally:
            conn.close()
        return self._row(row) if row is not None else None

    def count_since(
        self, persona_id: str, since: float, *, actor: str | None = None
    ) -> int:
        """Count versions after ``since``, optionally only from one actor.

        The growth budget filters on ``actor='model'``: a baseline row written at
        startup and an operator rollback are not model writes and must not consume
        the model's hourly allowance.
        """
        sql = (
            "SELECT COUNT(*) FROM persona_versions "
            "WHERE persona_id = ? AND created_at >= ?"
        )
        params: list[object] = [persona_id, since]
        if actor:
            sql += " AND actor = ?"
            params.append(actor)
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row is not None else 0

    def latest_restorable(
        self, persona_id: str, *, limit: int = 20
    ) -> PersonaVersion | None:
        """Newest version whose payload can actually rebuild a card.

        Used when a file is unreadable: "restore the last version" is only useful
        if that version parses.
        """
        from soapbot.ai.persona import persona_from_payload

        for candidate in self.list_versions(persona_id, limit=limit):
            try:
                persona_from_payload(candidate.payload, persona_id)
            except Exception as exc:
                logger.warning(
                    "persona version unusable persona=%s version=%s err=%s",
                    persona_id,
                    candidate.version,
                    type(exc).__name__,
                )
                continue
            return candidate
        return None
