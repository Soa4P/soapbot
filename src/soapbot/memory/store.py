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

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, func, select, text

from soapbot.memory.db import (
    Database,
    KnowledgeRow,
    MemoryRow,
    MessageRow,
    SummaryRow,
    vector_to_blob,
)

logger = logging.getLogger(__name__)

RRF_K = 60


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
        async with self.db.session_factory()() as session:
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
            await session.commit()
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
                vectors = await self._embedder.embed([content])
                vector = vectors[0] if vectors else []
            except Exception as exc:
                # A memory without an embedding is still useful via BM25, so this
                # must not abort the write.
                logger.warning("embedding failed for memory, storing without vector: %s", exc)

        async with self.db.session_factory()() as session:
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
            await session.commit()
            return row.id

    async def _fts_insert(self, session, table: str, content: str, row_id: int) -> None:
        """Delegate to the shared module-level helper."""
        await _fts_index(session, table, content, row_id)

    async def save_summary(self, session_key: str, summary: str, folded: int) -> None:
        async with self.db.session_factory()() as session:
            session.add(
                SummaryRow(
                    session_key=session_key,
                    summary=summary,
                    folded_message_count=folded,
                    created_at=time.time(),
                )
            )
            await session.commit()

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

    async def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
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
            rows = (await session.execute(stmt)).all()
        return [
            {"session_key": r[0], "message_count": r[1], "last_at": r[2]} for r in rows
        ]

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
            vectors = await self._embedder.embed([query])
        except Exception as exc:
            logger.warning("query embedding failed, keyword-only recall: %s", exc)
            return []
        if not vectors:
            return []
        qvec = vectors[0]

        async with self.db.session_factory()() as session:
            stmt = select(MemoryRow).where(MemoryRow.embedding.is_not(None))
            if scope:
                stmt = stmt.where(MemoryRow.scope.in_([scope, ""]))
            if layers:
                stmt = stmt.where(MemoryRow.layer.in_([str(layer) for layer in layers]))
            rows = (await session.execute(stmt)).scalars().all()

        import numpy as np

        q = np.asarray(qvec, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []

        scored: list[tuple[float, MemoryRow]] = []
        for r in rows:
            if not r.embedding or r.embedding_dim != len(qvec):
                continue
            v = np.frombuffer(r.embedding, dtype=np.float32)
            vn = np.linalg.norm(v)
            if vn == 0:
                continue
            cosine = float(np.dot(q, v) / (qn * vn))
            if cosine <= 0:
                continue
            scored.append((cosine, r))

        scored.sort(key=lambda x: x[0], reverse=True)
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
            for _, r in scored[:limit]
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
        async with self.db.session_factory()() as session:
            for mid in ids:
                row = await session.get(MemoryRow, mid)
                if row is not None:
                    row.access_count += 1
                    row.accessed_at = time.time()
            await session.commit()

    async def count_memories(self, layer: MemoryLayer | None = None) -> int:
        async with self.db.session_factory()() as session:
            stmt = select(func.count(MemoryRow.id))
            if layer is not None:
                stmt = stmt.where(MemoryRow.layer == str(layer))
            return int((await session.execute(stmt)).scalar_one())

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
        async with self.db.session_factory()() as session:
            row = await session.get(MemoryRow, memory_id)
            if row is None:
                return False
            await session.execute(
                text("DELETE FROM memories_fts WHERE row_id = :r"), {"r": memory_id}
            )
            await session.delete(row)
            await session.commit()
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

        async with self.db.session_factory()() as session:
            ids: list[int] = []
            for i, chunk in enumerate(chunks):
                vec = vectors[i] if i < len(vectors) else []
                row = KnowledgeRow(
                    doc_id=doc_id,
                    title=title,
                    chunk_index=i,
                    content=chunk,
                    embedding=vector_to_blob(vec) if vec else None,
                    embedding_dim=len(vec),
                    created_at=time.time(),
                )
                session.add(row)
                await session.flush()
                ids.append(row.id)
                await _fts_index(session, "knowledge_fts", chunk, row.id)
            await session.commit()
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
                import numpy as np

                q = np.asarray(qvec, dtype=np.float32)
                qn = np.linalg.norm(q)
                async with self.db.session_factory()() as session:
                    rows = (
                        await session.execute(
                            select(KnowledgeRow).where(KnowledgeRow.embedding.is_not(None))
                        )
                    ).scalars().all()
                scored: list[tuple[float, KnowledgeRow]] = []
                for r in rows:
                    if not r.embedding or r.embedding_dim != len(qvec):
                        continue
                    v = np.frombuffer(r.embedding, dtype=np.float32)
                    vn = np.linalg.norm(v)
                    if vn == 0 or qn == 0:
                        continue
                    scored.append((float(np.dot(q, v) / (qn * vn)), r))
                scored.sort(key=lambda x: x[0], reverse=True)
                for i, (_, r) in enumerate(scored[: limit * 2]):
                    entry = results.setdefault(
                        r.id,
                        {"id": r.id, "title": r.title, "content": r.content, "score": 0.0},
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
        async with self.db.session_factory()() as session:
            ids = (
                await session.execute(
                    select(KnowledgeRow.id).where(KnowledgeRow.doc_id == doc_id)
                )
            ).scalars().all()
            for kid in ids:
                await session.execute(
                    text("DELETE FROM knowledge_fts WHERE row_id = :r"), {"r": kid}
                )
            await session.execute(delete(KnowledgeRow).where(KnowledgeRow.doc_id == doc_id))
            await session.commit()
            return len(ids)


def content_fingerprint(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()[:16]
