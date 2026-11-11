"""Three-layer memory store and hybrid retrieval.

Layers:
  * **working**  — volatile, TTL, mirrored in ``SessionStore``; not embedded.
  * **episodic** — timestamped events ("用户在群里说了X"). Cheap to write, high recall.
  * **semantic** — distilled durable facts ("小明喜欢猫"). Higher weight in ranking.

Retrieval fuses two independent signals with **Reciprocal Rank Fusion**:

    score = Σ 1 / (k + rank_i)      (k = 60, the standard RRF constant)

Why RRF instead of weighted score addition: cosine similarity and BM25 live on
incompatible scales, and normalising them per-query is unstable when the result
set is small. RRF only uses *ranks*, so it behaves predictably regardless of the
underlying distributions — and it degrades gracefully when one channel returns
nothing (e.g. FTS5 unavailable, or no embedding provider configured).

Neither channel alone is sufficient:
- vectors miss exact identifiers (names, numbers) that BM25 nails
- BM25 misses paraphrase ("喜欢猫" vs "养了只喵")
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, func, select, text, update

from soapbot.config import settings
from soapbot.memory.db import (
    Database,
    KnowledgeRow,
    MemoryRow,
    MessageRow,
    SummaryRow,
    vector_to_blob,
)
from soapbot.memory.vectors import VectorCandidate, rank_by_cosine

logger = logging.getLogger(__name__)

RRF_K = 60


def _embed_input(text: str) -> str:
    """Bound what is sent to the embedding provider.

    Two reasons, and the second is the one that bites. Cost: providers bill by token, and
    a pasted document embedded in full is a bill nobody approved. Behaviour: models have
    a context limit and the outcome of exceeding it differs by provider — some truncate,
    some error, some silently return a vector of a different dimension. Truncating here
    makes the behaviour ours and identical everywhere, and matching truncation is applied
    to the query so a stored vector and a query vector are comparable.
    """
    # Honoured exactly when positive, rather than floored at some "sensible" minimum: an
    # operator who sets 50 because that is what their provider measures in is entitled to
    # 50. Only a non-positive value is treated as unset, since truncating to zero would
    # silently embed an empty string.
    limit = settings.max_embedding_chars if settings.max_embedding_chars > 0 else 2000
    if len(text) <= limit:
        return text
    logger.debug("truncating embedding input from %d to %d chars", len(text), limit)
    return text[:limit]


class MemoryLayer(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass(slots=True)
class MemoryItem:
    id: int
    layer: str
    content: str
    scope: str = ""
    subject: str = ""
    importance: float = 0.5
    created_at: float = 0.0
    score: float = 0.0
    source: str = ""
    """Which retrieval channel produced it: vector / keyword / both."""


@dataclass(slots=True)
class RecallResult:
    items: list[MemoryItem] = field(default_factory=list)
    vector_hits: int = 0
    keyword_hits: int = 0
    fused: bool = False
    query: str = ""

    def to_prompt(self, limit: int = 8) -> str:
        if not self.items:
            return ""
        lines = [f"- {it.content}" for it in self.items[:limit]]
        return "你记得以下与当前对话相关的信息：\n" + "\n".join(lines)


_CJK_CLASS = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af"
_TOKEN_RE = re.compile(rf"[{_CJK_CLASS}]+|[^\W{_CJK_CLASS}]+", re.UNICODE)


def _terms(text_value: str) -> list[str]:
    """Tokenise for FTS5.

    FTS5's ``unicode61`` has no CJK segmenter, so we must produce CJK bigrams
    ourselves: 「小明喜欢猫」 -> 小明 / 明喜 / 喜欢 / 欢猫.

    IMPORTANT: CJK runs must be detected *per character class*, not per
    ``\\w`` chunk. A mixed string like 「我的生日是7月12日」 is a single ``\\w`` run,
    but treating it as one token makes the query 「生日」 unmatchable. Splitting on
    character class keeps CJK bigrams and digit runs separate.
    """
    out: list[str] = []
    for chunk in _TOKEN_RE.findall(text_value or ""):
        if not chunk:
            continue
        if re.fullmatch(rf"[{_CJK_CLASS}]+", chunk):
            if len(chunk) == 1:
                out.append(chunk)
            else:
                out.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
        else:
            out.append(chunk.lower())
    return out


def _fts_query(query: str) -> str:
    terms = _terms(query)
    if not terms:
        return ""
    # Quote each term so punctuation cannot break FTS5 syntax.
    return " OR ".join(f'"{t}"' for t in terms[:16])


#: The only FTS5 mirror tables that exist. ``table`` is interpolated into SQL (a
#: table name cannot be a bound parameter in SQLite), so it must never be
#: attacker-influenced. Today every caller passes a literal, but a future caller
#: taking the name from config or a plugin would turn this into SQL injection with
#: no visible change at the call site. The allow-list makes that mistake loud.
#: Source of truth is ``db._create_fts``; keep this list in sync with it.
_FTS_TABLES: frozenset[str] = frozenset(
    {"messages_fts", "memories_fts", "knowledge_fts"}
)


async def _fts_index(session, table: str, content: str, row_id: int) -> None:
    """Insert one row into an FTS5 mirror table (module-level, shared by both stores).

    使用 SAVEPOINT：插入失败只回滚这次索引写入，不会把同事务里刚写入的业务行
    一起拖进无效事务。失败仍会被记录，而不是静默丢索引。
    """
    if table not in _FTS_TABLES:
        # Refuse rather than quote: a quoting helper invites "just pass it through".
        raise ValueError(f"unknown FTS table {table!r}; expected one of {sorted(_FTS_TABLES)}")
    try:
        async with session.begin_nested():
            await session.execute(
                text(f"INSERT INTO {table}(content, row_id) VALUES (:c, :r)"),
                {"c": _index_text(content), "r": row_id},
            )
    except Exception as exc:
        logger.warning("FTS index insert failed for %s (row %s): %s", table, row_id, exc)


async def _fts_index_many(session, table: str, items: list[tuple[str, int]]) -> None:
    """Index many FTS rows in one statement instead of one per chunk.

    ``add_document`` used to ``flush()`` + ``INSERT`` per chunk while holding the write
    lock, so a long document stalled every other writer for as many round trips as it
    had chunks. A single executemany keeps the lock hold proportional to the SQL work
    rather than to the number of awaits.

    The SAVEPOINT is still there: FTS indexing is best-effort, and a failure must not
    poison the transaction that just wrote the real document rows.
    """
    if table not in _FTS_TABLES:
        raise ValueError(f"unknown FTS table {table!r}; expected one of {sorted(_FTS_TABLES)}")
    if not items:
        return
    try:
        async with session.begin_nested():
            await session.execute(
                text(f"INSERT INTO {table}(content, row_id) VALUES (:c, :r)"),
                [{"c": _index_text(content), "r": row_id} for content, row_id in items],
            )
    except Exception as exc:
        logger.warning("FTS batch index insert failed for %s (%d rows): %s", table, len(items), exc)


def _index_text(value: str) -> str:
    """Render text for the FTS5 index.

    CRITICAL: FTS5's ``unicode61`` tokeniser does **not** segment CJK — it treats
    a whole run of Han characters as a single token. Indexing 「小明的生日」 verbatim
    makes the query 「生日」 unmatchable (this was a real bug: keyword search
    silently returned zero results for every Chinese query).

    The fix is to index the same bigrams we query with, so both sides agree:
        「小明生日」 -> "小明 明生 生日"
    ASCII is kept as lowercased words.
    """
    return " ".join(_terms(value))


class MemoryStore:
    def __init__(self, db: Database, embedder=None) -> None:
        self.db = db
        self._embedder = embedder

    def set_embedder(self, embedder) -> None:
        """``embedder`` is any object with ``async embed(list[str]) -> list[list[float]]``."""
        self._embedder = embedder

    # ------------------------------------------------------------------ writes
    async def archive_message(
        self,
        *,
        session_key: str,
        role: str,
        content: str,
        adapter: str = "",
        scene: str = "group",
        group_id: str = "",
        user_id: str = "",
        user_name: str = "",
        image_desc: str = "",
        message_id: str = "",
        trace_id: str = "",
        created_at: float | None = None,
    ) -> int:
        """Append one message. Never mutates existing rows."""
        ts = created_at if created_at is not None else time.time()
        async with self.db.write() as session:
            row = MessageRow(
                session_key=session_key,
                adapter=adapter,
                scene=scene,
                group_id=group_id,
                user_id=user_id,
                user_name=user_name,
                role=role,
                content=content,
                image_desc=image_desc,
                message_id=message_id,
                trace_id=trace_id,
                created_at=ts,
            )
            session.add(row)
            # flush 取到自增 id 后再写 FTS，最后统一 commit：
            # 若分两次提交，会出现「行已可见但索引缺失」的窗口，期间检索静默漏命中。
            await session.flush()
            if content:
                await self._fts_insert(session, "messages_fts", content, row.id)
            return row.id

    async def add_memory(
        self,
        *,
        content: str,
        layer: MemoryLayer = MemoryLayer.SEMANTIC,
        scope: str = "",
        subject: str = "",
        importance: float = 0.5,
        source_message_id: str = "",
        keywords: str = "",
        embed: bool = True,
    ) -> int:
        if not content.strip():
            raise ValueError("memory content must not be empty")
        vector: list[float] = []
        if embed and self._embedder is not None:
            try:
                vectors = await self._embedder.embed([_embed_input(content)])
                vector = vectors[0] if vectors else []
            except Exception as exc:
                # A memory without an embedding is still useful via BM25, so this
                # must not abort the write.
                logger.warning("embedding failed for memory, storing without vector: %s", exc)

        async with self.db.write() as session:
            row = MemoryRow(
                layer=str(layer),
                scope=scope,
                subject=subject,
                content=content,
                keywords=keywords or " ".join(_terms(content)[:20]),
                importance=importance,
                embedding=vector_to_blob(vector) if vector else None,
                embedding_dim=len(vector),
                source_message_id=source_message_id,
                created_at=time.time(),
                accessed_at=time.time(),
            )
            session.add(row)
            # 原子写入：行与索引必须在同一事务里提交，否则检索端可能读到
            # 「记忆存在但索引缺失」的中间态（曾导致 /recall 无结果）。
            await session.flush()
            await self._fts_insert(session, "memories_fts", content, row.id)
            return row.id

    async def _fts_insert(self, session, table: str, content: str, row_id: int) -> None:
        """Delegate to the shared module-level helper."""
        await _fts_index(session, table, content, row_id)

    async def save_summary(self, session_key: str, summary: str, folded: int) -> None:
        """Persist a rolling summary, refusing one that asserts authority.

        Same guard as :meth:`add_memory`, and for the same reason: a summary is a
        persistence layer for whatever it contains. It is re-fed on every later turn, so a
        planted claim in it outlives the message that carried it — which is the definition
        of memory poisoning.

        Returns nothing either way. Callers that need to know whether it was stored should
        call :func:`soapbot.security.injection.vet_memory` first; refusing here is the last
        line, not the only one.
        """
        from soapbot.security.injection import vet_memory

        allowed, reason = vet_memory(summary)
        if not allowed:
            logger.warning(
                "refusing to persist a summary for %s: %s", session_key, reason
            )
            return

        async with self.db.write() as session:
            session.add(
                SummaryRow(
                    session_key=session_key,
                    summary=summary,
                    folded_message_count=folded,
                    created_at=time.time(),
                )
            )

    async def latest_summary(self, session_key: str) -> str:
        async with self.db.session_factory()() as session:
            result = await session.execute(
                select(SummaryRow.summary)
                .where(SummaryRow.session_key == session_key)
                .order_by(SummaryRow.id.desc())
                .limit(1)
            )
            row = result.first()
            return str(row[0]) if row else ""

    # ------------------------------------------------------------------ reads
    async def history(
        self, session_key: str, *, limit: int = 40, before: float | None = None
    ) -> list[dict[str, Any]]:
        """Recent turns as OpenAI-style dicts, oldest first."""
        async with self.db.session_factory()() as session:
            stmt = select(MessageRow).where(MessageRow.session_key == session_key)
            if before is not None:
                stmt = stmt.where(MessageRow.created_at < before)
            stmt = stmt.order_by(MessageRow.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

        rows = list(reversed(rows))
        out: list[dict[str, Any]] = []
        for r in rows:
            content = r.content
            if r.image_desc:
                content = f"{content}\n[图片内容：{r.image_desc}]".strip()
            out.append({"role": r.role, "content": content})
        return out

    async def find_message(
        self, session_key: str, message_id: str
    ) -> dict[str, Any] | None:
        """Look up one archived message *inside a session*, by platform message id.

        Exists for moderation: ``/recall <id>`` must not be a way to delete a
        message in a group the caller is not in. The platform's delete API takes a
        bare message id with no group scope, so the only check available is the
        host's own record of having seen that id in this session. Scoping the query
        by ``session_key`` is what makes that check real rather than assumed —
        matching on id alone would find another group's message and approve the
        recall.
        """
        if not session_key or not message_id:
            return None
        async with self.db.session_factory()() as session:
            stmt = (
                select(MessageRow)
                .where(
                    MessageRow.session_key == session_key,
                    MessageRow.message_id == message_id,
                )
                .order_by(MessageRow.id.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "id": row.id,
            "role": row.role,
            "user_id": row.user_id,
            "user_name": row.user_name,
            "content": row.content,
            "message_id": row.message_id,
            "created_at": row.created_at,
        }

    async def timeline(
        self, session_key: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Full archive view for the WebUI timeline (includes ids and times)."""
        async with self.db.session_factory()() as session:
            stmt = (
                select(MessageRow)
                .where(MessageRow.session_key == session_key)
                .order_by(MessageRow.id.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "image_desc": r.image_desc,
                "user_name": r.user_name,
                "created_at": r.created_at,
                "trace_id": r.trace_id,
            }
            for r in reversed(rows)
        ]

    async def list_sessions(
        self,
        *,
        limit: int = 50,
        session_keys: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Newest sessions first, optionally restricted to the caller's grants.

        ``session_keys`` is pushed into SQL rather than applied to the result: a member
        granted one quiet group would otherwise disappear as soon as 200 busier sessions
        pushed its row past ``limit``, and the page would look empty rather than
        unauthorised.
        """
        async with self.db.session_factory()() as session:
            stmt = (
                select(
                    MessageRow.session_key,
                    func.count(MessageRow.id).label("cnt"),
                    func.max(MessageRow.created_at).label("last_at"),
                )
                .group_by(MessageRow.session_key)
                .order_by(func.max(MessageRow.created_at).desc())
                .limit(limit)
            )
            if session_keys is not None:
                allowed = list(session_keys)
                if not allowed:
                    return []
                stmt = stmt.where(MessageRow.session_key.in_(allowed))
            rows = (await session.execute(stmt)).all()
        return [
            {"session_key": r[0], "message_count": r[1], "last_at": r[2]} for r in rows
        ]

    async def messages_since(
        self,
        session_key: str,
        *,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Ascending page after a cursor.

        ``after_id`` rather than an offset: a client that pages while the bot keeps
        archiving must not see the same message twice or skip one when a new row lands
        between two requests. ``id`` is monotonic in SQLite, so it is the cursor.
        """
        async with self.db.session_factory()() as session:
            rows = (
                (
                    await session.execute(
                        select(MessageRow)
                        .where(
                            MessageRow.session_key == session_key,
                            MessageRow.id > after_id,
                        )
                        .order_by(MessageRow.id.asc())
                        .limit(max(1, min(limit, 200)))
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "id": row.id,
                "session_key": row.session_key,
                "role": row.role,
                "content": row.content,
                "image_desc": row.image_desc,
                "user_id": row.user_id,
                "user_name": row.user_name,
                "adapter": row.adapter,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def add_note(
        self,
        *,
        session_key: str,
        content: str,
        user_id: str,
        user_name: str,
    ) -> dict[str, Any]:
        """Append an operator note. Never sent anywhere.

        The short-circuit is structural: this method only writes a row. There is no
        adapter parameter to misuse, so a later refactor cannot accidentally turn a
        note into a QQ message without changing the call graph.
        """
        text = content.strip()
        if not text:
            raise ValueError("note content is empty")
        row_id = await self.archive_message(
            session_key=session_key,
            role="note",
            content=text,
            adapter="web",
            scene="group" if "group" in session_key else "private",
            user_id=user_id,
            user_name=user_name,
        )
        return {
            "id": row_id,
            "session_key": session_key,
            "role": "note",
            "content": text,
            "user_id": user_id,
            "user_name": user_name,
            "adapter": "web",
            "created_at": time.time(),
        }

    # ------------------------------------------------------------------ search
    async def recall(
        self,
        query: str,
        *,
        scope: str = "",
        limit: int = 8,
        layers: list[MemoryLayer] | None = None,
    ) -> RecallResult:
        """Hybrid retrieval over long-term memory, fused with RRF."""
        if not query.strip():
            return RecallResult(query=query)

        # ``limit`` reaches here from callers, and a recalled item costs prompt tokens on
        # every later turn. Clamped rather than trusted: the ceiling is what bounds the
        # cost of a poisoned or simply busy scope, and it is the only place the number is
        # enforced (a caller could otherwise ask for 10_000 and get a prompt nobody can
        # afford).
        limit = max(1, min(limit, settings.max_recall_items))

        vector_hits = await self._vector_search(query, scope=scope, limit=limit * 3, layers=layers)
        keyword_hits = await self._keyword_search(query, scope=scope, limit=limit * 3, layers=layers)

        result = RecallResult(
            query=query,
            vector_hits=len(vector_hits),
            keyword_hits=len(keyword_hits),
            fused=bool(vector_hits and keyword_hits),
        )

        scores: dict[int, float] = {}
        payload: dict[int, MemoryItem] = {}
        channels: dict[int, set[str]] = {}

        for rank, item in enumerate(vector_hits):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (RRF_K + rank + 1)
            payload[item.id] = item
            channels.setdefault(item.id, set()).add("vector")

        for rank, item in enumerate(keyword_hits):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (RRF_K + rank + 1)
            payload.setdefault(item.id, item)
            channels.setdefault(item.id, set()).add("keyword")

        # Importance nudges ties apart without letting it dominate rank order.
        for mid, base in scores.items():
            item = payload[mid]
            scores[mid] = base * (0.8 + 0.4 * max(0.0, min(1.0, item.importance)))

        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        for mid, score in ordered:
            item = payload[mid]
            item.score = round(score, 6)
            item.source = "+".join(sorted(channels.get(mid, set())))
            result.items.append(item)

        await self._touch([it.id for it in result.items])
        return result

    async def _vector_search(
        self, query: str, *, scope: str, limit: int, layers: list[MemoryLayer] | None
    ) -> list[MemoryItem]:
        if self._embedder is None:
            return []
        try:
            vectors = await self._embedder.embed([_embed_input(query)])
        except Exception as exc:
            logger.warning("query embedding failed, keyword-only recall: %s", exc)
            return []
        if not vectors:
            return []
        qvec = vectors[0]

        # Phase 1: only the columns the scan needs. Loading full ORM objects for
        # every embedded row paid for content/keywords text that at most ``limit``
        # of them will ever contribute to the prompt.
        async with self.db.session_factory()() as session:
            stmt = select(
                MemoryRow.id, MemoryRow.embedding, MemoryRow.embedding_dim
            ).where(MemoryRow.embedding.is_not(None))
            if scope:
                stmt = stmt.where(MemoryRow.scope.in_([scope, ""]))
            if layers:
                stmt = stmt.where(MemoryRow.layer.in_([str(layer) for layer in layers]))
            candidates = [
                VectorCandidate(row[0], row[1], row[2])
                for row in (await session.execute(stmt)).all()
            ]

        ranking = rank_by_cosine(candidates, qvec, limit=limit)
        if not ranking.query_usable:
            logger.warning("query embedding is not finite; falling back to keyword recall")
            return []
        if ranking.dropped:
            # Reported rather than silent: a row with a broken vector keeps taking up
            # space and never matches anything, which looks like "memory does not work"
            # and is impossible to diagnose from the outside.
            logger.warning(
                "skipped %d memory row(s) with unusable embeddings scope=%s",
                ranking.dropped,
                scope,
            )
        if not ranking.hits:
            return []

        # Phase 2: fetch display columns for the winners only. The second round trip
        # is cheaper than carrying every row's text through the scoring loop.
        top_ids = [row_id for _, row_id in ranking.hits]
        async with self.db.session_factory()() as session:
            rows = (
                await session.execute(select(MemoryRow).where(MemoryRow.id.in_(top_ids)))
            ).scalars().all()
        by_id = {row.id: row for row in rows}
        return [
            MemoryItem(
                id=r.id,
                layer=r.layer,
                content=r.content,
                scope=r.scope,
                subject=r.subject,
                importance=r.importance,
                created_at=r.created_at,
            )
            for _, row_id in ranking.hits
            if (r := by_id.get(row_id)) is not None
        ]

    async def _keyword_search(
        self, query: str, *, scope: str, limit: int, layers: list[MemoryLayer] | None
    ) -> list[MemoryItem]:
        fts_q = _fts_query(query)
        if not fts_q:
            return []
        sql = (
            "SELECT m.id, m.layer, m.content, m.scope, m.subject, m.importance, "
            "m.created_at, bm25(memories_fts) AS rank "
            "FROM memories_fts JOIN memories m ON m.id = memories_fts.row_id "
            "WHERE memories_fts MATCH :q"
        )
        params: dict[str, Any] = {"q": fts_q, "limit": limit}
        if scope:
            sql += " AND (m.scope = :scope OR m.scope = '')"
            params["scope"] = scope
        if layers:
            placeholders = ",".join(f":l{i}" for i in range(len(layers)))
            sql += f" AND m.layer IN ({placeholders})"
            for i, layer in enumerate(layers):
                params[f"l{i}"] = str(layer)
        sql += " ORDER BY rank LIMIT :limit"

        try:
            async with self.db.session_factory()() as session:
                rows = (await session.execute(text(sql), params)).all()
        except Exception as exc:
            logger.debug("fts query failed (keyword channel skipped): %s", exc)
            return []

        return [
            MemoryItem(
                id=r[0],
                layer=r[1],
                content=r[2],
                scope=r[3],
                subject=r[4],
                importance=r[5],
                created_at=r[6],
            )
            for r in rows
        ]

    async def _touch(self, ids: list[int]) -> None:
        if not ids:
            return
        # One UPDATE, not one SELECT + one UPDATE per recalled memory. ``recall`` can
        # return up to ``MAX_RECALL_ITEMS`` rows and holds the write lock the whole
        # time, so the old loop made every other writer wait for N round trips.
        # ``in_`` binds each id as a parameter; nothing is interpolated into the SQL.
        async with self.db.write() as session:
            await session.execute(
                update(MemoryRow)
                .where(MemoryRow.id.in_(ids))
                .values(access_count=MemoryRow.access_count + 1, accessed_at=time.time())
            )

    async def count_memories(self, layer: MemoryLayer | None = None) -> int:
        async with self.db.session_factory()() as session:
            stmt = select(func.count(MemoryRow.id))
            if layer is not None:
                stmt = stmt.where(MemoryRow.layer == str(layer))
            return int((await session.execute(stmt)).scalar_one())

    async def count_by_layer(self) -> dict[str, int]:
        """Row counts for every layer in one query.

        The panel asks for all layers on one screen. Looping ``count_memories(layer)``
        there cost four to five round trips, and each one could observe a *different*
        snapshot — so the total and the sum of its parts could disagree under load.
        One ``GROUP BY`` answers both questions from a single read.
        """
        async with self.db.session_factory()() as session:
            stmt = select(MemoryRow.layer, func.count(MemoryRow.id)).group_by(
                MemoryRow.layer
            )
            rows = (await session.execute(stmt)).all()
        return {str(layer): int(count) for layer, count in rows}

    async def list_memories(
        self,
        *,
        scope: str = "",
        layer: MemoryLayer | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryItem]:
        """Recent memories, optionally narrowed to one scope or layer.

        Exists because the panel could show *counts* per layer and the archived
        *messages* of a session, but never the memory rows themselves — the only way to
        see one was to read the database, and the only way to remove one was
        ``/forget`` in the group chat. A management page that cannot show the thing it
        manages is a dashboard, not a tool.

        Ordered by ``id`` descending rather than ``created_at``: the id is the primary
        key and the value the delete endpoint takes, so the list order matches the
        handles the operator is about to use. ``created_at`` can tie across a batch
        insert, which would make paging skip or repeat rows.
        """
        async with self.db.session_factory()() as session:
            stmt = select(MemoryRow).order_by(MemoryRow.id.desc()).limit(limit).offset(offset)
            if scope:
                stmt = stmt.where(MemoryRow.scope == scope)
            if layer is not None:
                stmt = stmt.where(MemoryRow.layer == str(layer))
            rows = (await session.execute(stmt)).scalars().all()
        return [
            MemoryItem(
                id=row.id,
                layer=row.layer,
                content=row.content,
                scope=row.scope,
                subject=row.subject,
                importance=row.importance,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_memory(self, memory_id: int) -> MemoryItem | None:
        """Fetch one memory regardless of scope.

        Used by ``/forget`` to verify ownership *before* deleting. Without this
        lookup the command could only take the caller's word for it that the row
        belongs to them, and an integer id is trivially enumerable.
        """
        async with self.db.session_factory()() as session:
            row = await session.get(MemoryRow, memory_id)
            if row is None:
                return None
            return MemoryItem(
                id=row.id,
                layer=row.layer,
                content=row.content,
                scope=row.scope,
                subject=row.subject,
                importance=row.importance,
                created_at=row.created_at,
            )

    async def delete_memory(self, memory_id: int) -> bool:
        async with self.db.write() as session:
            row = await session.get(MemoryRow, memory_id)
            if row is None:
                return False
            await session.execute(
                text("DELETE FROM memories_fts WHERE row_id = :r"), {"r": memory_id}
            )
            await session.delete(row)
            return True


class KnowledgeBase:
    """Document chunks for RAG."""

    def __init__(self, db: Database, embedder=None, chunk_size: int = 400, overlap: int = 60) -> None:
        self.db = db
        self._embedder = embedder
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, content: str) -> list[str]:
        """Split on paragraph/sentence boundaries, never mid-sentence when avoidable."""
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if p.strip()]
        chunks: list[str] = []
        for para in paragraphs:
            if len(para) <= self.chunk_size:
                chunks.append(para)
                continue
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            current = ""
            for sent in sentences:
                if not sent:
                    continue
                if len(current) + len(sent) <= self.chunk_size:
                    current += sent
                else:
                    if current:
                        chunks.append(current)
                    current = sent[-self.chunk_size :]
            if current:
                chunks.append(current)
        if not chunks and content.strip():
            chunks = [content.strip()]
        return chunks

    async def add_document(self, doc_id: str, title: str, content: str) -> int:
        chunks = self.chunk(content)
        if not chunks:
            return 0

        vectors: list[list[float]] = []
        if self._embedder is not None:
            try:
                vectors = await self._embedder.embed(chunks)
            except Exception as exc:
                logger.warning("knowledge embedding failed, storing text only: %s", exc)

        async with self.db.write() as session:
            now = time.time()
            rows: list[KnowledgeRow] = []
            for i, chunk in enumerate(chunks):
                vec = vectors[i] if i < len(vectors) else []
                rows.append(
                    KnowledgeRow(
                        doc_id=doc_id,
                        title=title,
                        chunk_index=i,
                        content=chunk,
                        embedding=vector_to_blob(vec) if vec else None,
                        embedding_dim=len(vec),
                        created_at=now,
                    )
                )
            session.add_all(rows)
            # One flush for the whole document. SQLAlchemy still emits one INSERT per
            # row to collect autoincrement ids, but that is one unit of work rather
            # than N awaited flush/FTS pairs — the difference that held the write lock
            # for as long as the document was long.
            await session.flush()
            ids = [row.id for row in rows]
            await _fts_index_many(
                session, "knowledge_fts", list(zip(chunks, ids, strict=True))
            )
            return len(ids)

    async def ingest_document(
        self, doc_id: str, title: str, content: str
    ) -> dict[str, Any]:
        """Add or replace a document, returning what actually happened.

        ``add_document`` appends chunks; called twice with the same ``doc_id`` it
        produces two copies of every chunk, and the retriever then returns the same
        passage twice with double the score. That made re-uploading a corrected
        document worse than not re-uploading at all.

        Replacing is the honest semantic for "upload this file": the operator's
        intent is "this is the current content", not "add another copy". The old
        chunks are deleted first so a shortened document does not leave stale tail
        chunks answering queries with text that no longer exists.

        Returned counts rather than a bare int so the caller can tell "created" from
        "replaced" — the WebUI shows a different message for each, and an operator
        who uploaded the wrong file needs to know which one they overwrote.
        """
        if not content.strip():
            return {"doc_id": doc_id, "chunks": 0, "replaced": False}

        existed = any(
            d.get("doc_id") == doc_id for d in await self.list_documents()
        )
        if existed:
            await self.delete_document(doc_id)

        chunks = await self.add_document(doc_id, title, content)
        return {"doc_id": doc_id, "chunks": chunks, "replaced": existed}

    async def document_detail(self, doc_id: str) -> dict[str, Any] | None:
        """One document's chunks, in order, for the WebUI preview."""
        async with self.db.session_factory()() as session:
            rows = (
                await session.execute(
                    select(KnowledgeRow)
                    .where(KnowledgeRow.doc_id == doc_id)
                    .order_by(KnowledgeRow.chunk_index)
                )
            ).scalars().all()
        if not rows:
            return None
        return {
            "doc_id": doc_id,
            "title": rows[0].title,
            "chunks": [
                {"index": r.chunk_index, "content": r.content} for r in rows
            ],
            "chunk_count": len(rows),
            "created_at": rows[0].created_at,
        }

    async def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        results: dict[int, dict[str, Any]] = {}

        fts_q = _fts_query(query)
        if fts_q:
            try:
                async with self.db.session_factory()() as session:
                    rows = (
                        await session.execute(
                            text(
                                "SELECT k.id, k.title, k.content, bm25(knowledge_fts) AS rank "
                                "FROM knowledge_fts JOIN knowledge k ON k.id = knowledge_fts.row_id "
                                "WHERE knowledge_fts MATCH :q ORDER BY rank LIMIT :limit"
                            ),
                            {"q": fts_q, "limit": limit * 2},
                        )
                    ).all()
                for i, r in enumerate(rows):
                    results[r[0]] = {
                        "id": r[0],
                        "title": r[1],
                        "content": r[2],
                        "score": 1.0 / (RRF_K + i + 1),
                    }
            except Exception as exc:
                logger.debug("knowledge fts failed: %s", exc)

        if self._embedder is not None:
            try:
                qvec = (await self._embedder.embed([query]))[0]
                async with self.db.session_factory()() as session:
                    candidates = [
                        VectorCandidate(row[0], row[1], row[2])
                        for row in (
                            await session.execute(
                                select(
                                    KnowledgeRow.id,
                                    KnowledgeRow.embedding,
                                    KnowledgeRow.embedding_dim,
                                ).where(KnowledgeRow.embedding.is_not(None))
                            )
                        ).all()
                    ]
                ranking = rank_by_cosine(candidates, qvec, limit=limit * 2)
                if not ranking.query_usable:
                    logger.warning(
                        "knowledge query embedding is not finite; keyword-only recall"
                    )
                elif ranking.dropped:
                    logger.warning(
                        "skipped %d knowledge chunk(s) with unusable embeddings",
                        ranking.dropped,
                    )
                if ranking.hits:
                    # Only the winning chunks need their text. The old loop loaded
                    # every chunk's title/content as full ORM objects to rank them.
                    top_ids = [row_id for _, row_id in ranking.hits]
                    async with self.db.session_factory()() as session:
                        payload = (
                            await session.execute(
                                select(
                                    KnowledgeRow.id,
                                    KnowledgeRow.title,
                                    KnowledgeRow.content,
                                ).where(KnowledgeRow.id.in_(top_ids))
                            )
                        ).all()
                    by_id = {row[0]: (row[1], row[2]) for row in payload}
                    for i, (_, row_id) in enumerate(ranking.hits):
                        if row_id not in by_id:
                            continue
                        title, content = by_id[row_id]
                        entry = results.setdefault(
                            row_id,
                            {"id": row_id, "title": title, "content": content, "score": 0.0},
                        )
                        entry["score"] += 1.0 / (RRF_K + i + 1)
            except Exception as exc:
                logger.warning("knowledge vector search failed: %s", exc)

        ordered = sorted(results.values(), key=lambda r: r["score"], reverse=True)[:limit]
        return ordered

    async def list_documents(self) -> list[dict[str, Any]]:
        async with self.db.session_factory()() as session:
            stmt = (
                select(
                    KnowledgeRow.doc_id,
                    KnowledgeRow.title,
                    func.count(KnowledgeRow.id).label("chunks"),
                )
                .group_by(KnowledgeRow.doc_id, KnowledgeRow.title)
                .order_by(KnowledgeRow.doc_id)
            )
            rows = (await session.execute(stmt)).all()
        return [{"doc_id": r[0], "title": r[1], "chunks": r[2]} for r in rows]

    async def delete_document(self, doc_id: str) -> int:
        async with self.db.write() as session:
            ids = (
                await session.execute(
                    select(KnowledgeRow.id).where(KnowledgeRow.doc_id == doc_id)
                )
            ).scalars().all()
            # One DELETE with an IN subquery, not one per chunk. The document is still
            # present at this point, so the subquery resolves exactly the rows that are
            # about to be removed — no need to ship their ids back to Python first.
            await session.execute(
                text(
                    "DELETE FROM knowledge_fts WHERE row_id IN "
                    "(SELECT id FROM knowledge WHERE doc_id = :doc)"
                ),
                {"doc": doc_id},
            )
            await session.execute(delete(KnowledgeRow).where(KnowledgeRow.doc_id == doc_id))
            return len(ids)



