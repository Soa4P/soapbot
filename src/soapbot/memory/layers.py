"""The four memory layers, on top of the existing archive.

L0 is ``messages`` and is written by the pipeline, not here. This module owns the
three derived layers and the shared timeline:

* **L1** — rolling summaries, rebuildable from L0;
* **L2** — long-term facts, which already live in ``memories`` as ``layer=semantic``;
  the only thing added here is retirement (``archived``) instead of deletion;
* **L3** — an index of produced artifacts, with the body on disk and a sha256;
* **L4** — self notes: short, capped, deduplicated statements the bot makes about
  its own behaviour.

Nothing in this module is injected into a prompt on its own. ``stages`` decides what
is worth the tokens, and the cap here is what stops the store from growing until
"recent" means "the last two years".
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from soapbot.memory.db import (
    Database,
    MemoryArtifactRow,
    MemorySelfNoteRow,
    MemoryTimelineRow,
    SummaryRow,
)

logger = logging.getLogger(__name__)

#: Suffixes allowed for stored artifacts. The name is a sha256, so this list is not
#: a path-traversal control; it is here so a future caller cannot quietly start
#: writing executables into a directory the WebUI serves from.
ARTIFACT_SUFFIXES = frozenset({".txt", ".md", ".json", ".csv", ".html"})


def _norm_note(text: str) -> str:
    return " ".join(text.split()).lower()[:256]


def _row(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(row, name) for name in fields}


class MemoryLayers:
    """Read/write helpers for L1, L3, L4 and the shared timeline."""

    def __init__(
        self,
        db: Database,
        *,
        artifacts_dir: Path,
        self_note_limit: int = 40,
    ) -> None:
        self.db = db
        self.artifacts_dir = Path(artifacts_dir)
        self.self_note_limit = max(1, int(self_note_limit))

    def _session(self) -> Any:
        """A read-only session from the factory.

        ``Database.session()`` is an async *generator*, not a context manager, so it
        cannot be used with ``async with``; the factory can.
        """
        return self.db.session_factory()()

    # ---------------------------------------------------------------- L1
    async def add_summary(
        self,
        session_key: str,
        summary: str,
        *,
        window_start: float = 0.0,
        window_end: float = 0.0,
        folded_message_count: int = 0,
        model: str = "",
    ) -> int:
        async with self.db.write() as session:
            row = SummaryRow(
                session_key=session_key,
                summary=summary[:8000],
                folded_message_count=int(folded_message_count),
                created_at=time.time(),
                window_start=float(window_start),
                window_end=float(window_end),
                model=model[:64],
            )
            session.add(row)
            await session.flush()
            return int(row.id)

    async def latest_summary(self, session_key: str) -> dict[str, Any] | None:
        async with self._session() as session:
            row = (
                await session.execute(
                    select(SummaryRow)
                    .where(SummaryRow.session_key == session_key)
                    .order_by(SummaryRow.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return _row(
            row,
            ("summary", "folded_message_count", "created_at", "window_start", "window_end", "model"),
        )

    # ---------------------------------------------------------------- L2
    async def archive_fact(self, memory_id: int) -> bool:
        """Retire a fact without deleting it. Archived rows still explain history."""
        from soapbot.memory.db import MemoryRow

        async with self.db.write() as session:
            row = await session.get(MemoryRow, memory_id)
            if row is None:
                return False
            row.archived = 1
            return True

    # ---------------------------------------------------------------- L3
    async def add_artifact(
        self,
        *,
        session_key: str,
        title: str,
        data: bytes,
        suffix: str = ".txt",
    ) -> dict[str, Any]:
        suffix = suffix if suffix in ARTIFACT_SUFFIXES else ".txt"
        digest = hashlib.sha256(data).hexdigest()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        target = self.artifacts_dir / f"{digest}{suffix}"
        if not target.exists():
            staging = target.with_name(f".{digest}.tmp")
            staging.write_bytes(data)
            os.replace(staging, target)
        async with self.db.write() as session:
            row = MemoryArtifactRow(
                session_key=session_key,
                title=title[:256],
                sha256=digest,
                path=str(target),
                size=len(data),
                created_at=time.time(),
            )
            session.add(row)
            await session.flush()
            artifact_id = int(row.id)
        return {"id": artifact_id, "sha256": digest, "path": str(target), "size": len(data)}

    async def artifacts(self, session_key: str = "", *, limit: int = 10) -> list[dict[str, Any]]:
        query = select(MemoryArtifactRow).order_by(MemoryArtifactRow.id.desc()).limit(max(1, limit))
        if session_key:
            query = query.where(MemoryArtifactRow.session_key == session_key)
        async with self._session() as session:
            rows = (await session.execute(query)).scalars().all()
        return [
            _row(row, ("id", "title", "sha256", "path", "size", "created_at"))
            for row in rows
        ]

    def read_artifact(self, sha256: str) -> bytes | None:
        """Read by digest, and verify the bytes still match.

        The path comes from a row we wrote, but a database is not a trust boundary:
        a tampered row could point anywhere. Restricting to ``artifacts_dir`` and
        re-hashing keeps this honest.
        """
        for candidate in self.artifacts_dir.glob(f"{sha256}.*"):
            resolved = candidate.resolve()
            if self.artifacts_dir.resolve() not in resolved.parents:
                logger.warning("artifact outside the store: %s", candidate)
                continue
            data = resolved.read_bytes()
            if hashlib.sha256(data).hexdigest() == sha256:
                return data
            logger.warning("artifact digest mismatch: %s", candidate)
        return None

    # ---------------------------------------------------------------- L4
    async def add_self_note(self, content: str, *, source_session: str = "") -> bool:
        """Add or refresh a note. Returns ``True`` when a new row was created."""
        text = " ".join(content.split())[:500]
        if not text:
            return False
        norm = _norm_note(text)
        now = time.time()
        async with self.db.write() as session:
            existing = (
                await session.execute(
                    select(MemorySelfNoteRow).where(MemorySelfNoteRow.norm == norm)
                )
            ).scalar_one_or_none()
            if existing is not None:
                # Same sentence again: refresh recency instead of adding a duplicate.
                existing.updated_at = now
                return False
            session.add(
                MemorySelfNoteRow(
                    content=text,
                    norm=norm,
                    source_session=source_session[:128],
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()
            ids = (
                await session.execute(
                    select(MemorySelfNoteRow.id).order_by(
                        MemorySelfNoteRow.updated_at.asc(), MemorySelfNoteRow.id.asc()
                    )
                )
            ).scalars().all()
            overflow = len(ids) - self.self_note_limit
            if overflow > 0:
                await session.execute(
                    delete(MemorySelfNoteRow).where(
                        MemorySelfNoteRow.id.in_(ids[:overflow])
                    )
                )
        return True

    async def self_notes(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        cap = limit or self.self_note_limit
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(MemorySelfNoteRow)
                    .order_by(MemorySelfNoteRow.updated_at.desc())
                    .limit(max(1, cap))
                )
            ).scalars().all()
        return [_row(row, ("id", "content", "updated_at", "source_session")) for row in rows]

    async def delete_self_note(self, note_id: int) -> bool:
        async with self.db.write() as session:
            result = await session.execute(
                delete(MemorySelfNoteRow).where(MemorySelfNoteRow.id == note_id)
            )
            return bool(result.rowcount)

    # ---------------------------------------------------------------- timeline
    async def record_event(
        self,
        kind: str,
        summary: str,
        *,
        ref: str = "",
        session_key: str = "",
    ) -> None:
        """Append one event. Never raises into the caller: an event log is not worth
        failing a reply over."""
        try:
            async with self.db.write() as session:
                session.add(
                    MemoryTimelineRow(
                        kind=kind[:24],
                        ref=ref[:128],
                        summary=summary[:2000],
                        session_key=session_key[:128],
                        created_at=time.time(),
                    )
                )
        except Exception as exc:
            logger.warning("timeline write failed kind=%s err=%s", kind, type(exc).__name__)

    async def recent_events(
        self, session_key: str = "", *, limit: int = 10
    ) -> list[dict[str, Any]]:
        query = select(MemoryTimelineRow).order_by(MemoryTimelineRow.created_at.desc()).limit(
            max(1, limit)
        )
        if session_key:
            query = query.where(MemoryTimelineRow.session_key == session_key)
        async with self._session() as session:
            rows = (await session.execute(query)).scalars().all()
        return [
            _row(row, ("kind", "ref", "summary", "session_key", "created_at"))
            for row in rows
        ]
