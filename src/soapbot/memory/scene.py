"""Scene memory: a private index card and a portrait per conversation.

The problem this solves
-----------------------
Memory used to be one flat pool keyed by ``scope``. Retrieval fused vector and keyword
hits and returned whatever ranked highest, which works for "what did we say about X" and
badly for "who is this group". A group that has spent three months arguing about
mechanical keyboards and a group that coordinates a weekly book club produce the same
shape of result: a handful of recent fragments, with no sense of what the conversation
*is*.

Obsidian's answer to the same problem is the vault's structure, not its search. A note
sits in a folder, links to its neighbours, and has a title that says what it is about;
opening the vault gives you a map before it gives you a query box. The equivalents here:

* **An index card per scene** (:class:`SceneCard`) — the title, the one-line summary, the
  recurring topics, the people who matter. Small enough to inject on every turn, which is
  the point: it is the map, not the territory.
* **A portrait per scene** (:class:`ScenePortrait`) — the accumulated, slowly-changing
  understanding: what this group talks about, how it talks, what it keeps coming back to.
  Derived from memories rather than written by an operator, because the operator does not
  know either.
* **Links between memories** (:class:`MemoryLink`) — Obsidian's ``[[wikilink]]``, reduced
  to what is useful here: a typed, directed edge with a reason. "This fact is about the
  same person as that one" is what makes recall of one surface the other.

Why a card and a portrait are separate
--------------------------------------
They have different lifetimes and different costs. The card is cheap, changes every turn,
and is injected always. The portrait is expensive to compute, changes slowly, and is
injected when it is relevant. Merging them would mean either recomputing the portrait on
every message or injecting a stale card.

What this module deliberately does not do
-----------------------------------------
It does not generate text with a model. Everything here is derived from what is already
stored — counts, recency, co-occurrence. A model-written portrait is a model's opinion of
a group, and it would drift, hallucinate, and be impossible to audit. The portrait is a
*summary of evidence*, and every field can be traced back to rows.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, union_all
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from soapbot.memory.db import MemoryRow, SceneCardRow, SceneLinkRow, ScenePortraitRow

logger = logging.getLogger(__name__)

#: How many memories the card's topic list is drawn from.
#:
#: Bounded because the card is injected on every turn: a group with 50 000 memories must
#: not produce a 50 000-row scan for a six-word summary. Recency-weighted rather than
#: random, because a topic the group stopped discussing a year ago is not what the card
#: is for.
CARD_SOURCE_LIMIT = 200

#: Recurring topics kept on the card. Six is roughly the number a person can hold in
#: mind at once; more turns the card into a list nobody reads.
CARD_TOPIC_LIMIT = 6

#: People kept on the card. Same reasoning as topics.
CARD_PERSON_LIMIT = 5

#: Below this many memories a portrait is noise. "This group talks about X" from three
#: messages is a guess dressed as a summary.
PORTRAIT_MIN_MEMORIES = 12

#: Characters kept from a memory when building a portrait. The portrait is a summary;
#: long memories contribute their opening, which is where the subject usually is.
_PORTRAIT_SNIPPET = 80


@dataclass(slots=True)
class SceneCard:
    """The one-screen map of a conversation.

    Injected on every turn, so every field is bounded. ``summary`` is the only prose
    field and it is assembled from evidence, not generated.
    """

    scope: str
    title: str = ""
    """Human-readable name. Falls back to the scope's own id when unknown."""
    summary: str = ""
    """One or two sentences: what this conversation is about."""
    topics: list[str] = field(default_factory=list)
    """Recurring subjects, most-weighted first."""
    people: list[str] = field(default_factory=list)
    """Participants who recur in memories."""
    memory_count: int = 0
    updated_at: float = 0.0

    def to_prompt(self) -> str:
        """Render for the system prompt.

        Deliberately terse. This rides along with every request, and a card that costs
        200 tokens to say "this is a group chat" is a tax on every turn. Empty fields are
        omitted rather than rendered as "无" — a line saying nothing is worse than no line.

        Every field is cleaned and capped on the way out. The card is assembled from
        ``keywords``, ``subject`` and the scope id, none of which this module controls, and
        it is injected as *system* text on every turn — so a value that carries newlines or
        a paragraph of instructions would be read as part of the instructions. Sanitising
        at render time covers rows written before the sanitiser existed, which is the case
        that matters: the database already holds whatever the old code stored.
        """
        parts: list[str] = []
        title = _clean(self.title, _PROMPT_FIELD_LIMIT)
        if title:
            parts.append(f"当前场景：{title}")
        summary = _clean(self.summary, _PROMPT_TOTAL_LIMIT // 3)
        if summary:
            parts.append(summary)
        topics = [_clean(t, _PROMPT_FIELD_LIMIT) for t in self.topics[:CARD_TOPIC_LIMIT]]
        topics = [t for t in topics if t]
        if topics:
            parts.append("常聊话题：" + "、".join(topics))
        people = [_clean(p, _PROMPT_FIELD_LIMIT) for p in self.people[:CARD_PERSON_LIMIT]]
        people = [p for p in people if p]
        if people:
            parts.append("常见成员：" + "、".join(people))
        return "\n".join(parts)[:_PROMPT_TOTAL_LIMIT]


@dataclass(slots=True)
class ScenePortrait:
    """The slow-changing understanding of a conversation.

    Every field is derived from stored rows. ``confidence`` is the honest part: a portrait
    built from twelve memories is weaker evidence than one built from twelve hundred, and
    a caller that injects portraits should be able to tell the difference.
    """

    scope: str
    headline: str = ""
    """One sentence: what this group is for."""
    themes: list[str] = field(default_factory=list)
    """Longer-horizon subjects than the card's topics."""
    tone: str = ""
    """Observed register: question-heavy, joke-heavy, task-heavy."""
    recurring_questions: list[str] = field(default_factory=list)
    """Things this group asks repeatedly — the highest-value thing to remember."""
    memory_count: int = 0
    confidence: float = 0.0
    """0..1, from how much evidence the portrait rests on."""
    updated_at: float = 0.0

    def to_prompt(self) -> str:
        """Render for the system prompt, cleaned the same way as the card.

        ``recurring_questions`` is the dangerous field: it is verbatim memory content, so
        it is the one place where a whole user message reaches the system prompt. Capped
        harder than the rest and stripped of newlines for that reason.
        """
        parts: list[str] = []
        headline = _clean(self.headline, _PROMPT_TOTAL_LIMIT // 3)
        if headline:
            parts.append(f"场景画像：{headline}")
        themes = [_clean(t, _PROMPT_FIELD_LIMIT) for t in self.themes[:CARD_TOPIC_LIMIT]]
        themes = [t for t in themes if t]
        if themes:
            parts.append("长期主题：" + "、".join(themes))
        tone = _clean(self.tone, _PROMPT_FIELD_LIMIT)
        if tone:
            parts.append(f"交流风格：{tone}")
        questions = [
            _clean(q, _PROMPT_QUESTION_LIMIT) for q in self.recurring_questions[:3]
        ]
        questions = [q for q in questions if q]
        if questions:
            parts.append("反复被问到：" + "；".join(questions))
        return "\n".join(parts)[:_PROMPT_TOTAL_LIMIT]


@dataclass(slots=True)
class MemoryLink:
    """A typed edge between two memories — the ``[[wikilink]]``, with a reason.

    ``kind`` is a small closed set rather than free text. An open vocabulary of edge
    types sounds flexible and becomes unusable: nobody can query "all the edges" if every
    writer invents its own word.
    """

    source_id: int
    target_id: int
    kind: str
    """``same_subject`` / ``same_topic`` / ``elaborates`` / ``contradicts``."""
    weight: float = 1.0
    created_at: float = 0.0


#: The closed set of link kinds. Adding one is a schema change in spirit even though the
#: column is a string, because readers switch on it.
LINK_KINDS = frozenset({"same_subject", "same_topic", "elaborates", "contradicts"})

_QUESTION_RE = re.compile(r"[?？]\s*$")
_TOPIC_STOPWORDS = frozenset(
    {
        "什么", "怎么", "为什么", "可以", "这个", "那个", "我们", "你们", "他们",
        "现在", "今天", "明天", "昨天", "一下", "一个", "还是", "就是", "不是",
        "没有", "知道", "觉得", "可能", "应该", "需要", "已经", "因为", "所以",
    }
)


#: Characters kept from any single field that reaches the system prompt.
#:
#: The card and the portrait are injected on every turn, and their content comes from
#: ``keywords``, ``subject`` and memory ``content`` — all of which originate outside this
#: module. A topic is a word, not a paragraph; anything longer is either a bug in the
#: extractor or an attempt to smuggle instructions in through a field nobody thought to
#: vet. Truncation is the cheap half of that defence; stripping newlines is the other,
#: because a newline is what turns a list item into a new instruction.
_PROMPT_FIELD_LIMIT = 32

#: Characters kept from a recurring question. Longer than a topic because a question is
#: allowed to be a sentence, but still bounded.
_PROMPT_QUESTION_LIMIT = 60

#: Hard ceiling on a rendered card or portrait. A belt to the per-field braces: even if
#: every field were at its limit, the injected block cannot grow without bound.
_PROMPT_TOTAL_LIMIT = 600

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str, limit: int) -> str:
    """Make one prompt-bound field safe and small.

    Collapses every run of whitespace to a single space — which removes the newlines that
    would let a value impersonate a new instruction — and truncates. Applied to every
    field rather than to the ones that "look" user-controlled, because the distinction is
    exactly what a future edit gets wrong.
    """
    collapsed = _WHITESPACE_RE.sub(" ", text or "").strip()
    return collapsed[:limit]


def _keywords_of(row: MemoryRow) -> list[str]:
    """Topic tokens for one memory.

    ``keywords`` is already a space-joined token list written at insert time, so this
    reuses that work rather than re-tokenising content. Stopwords are dropped because
    "什么" and "可以" would otherwise be the top topics of every Chinese group chat.

    Every token is also cleaned and length-capped here rather than at render time: the
    card's topic list is what reaches the prompt, and a token long enough to carry an
    instruction is not a topic.
    """
    raw = (row.keywords or "").split()
    out: list[str] = []
    for token in raw:
        if not token or token in _TOPIC_STOPWORDS:
            continue
        cleaned = _clean(token, _PROMPT_FIELD_LIMIT)
        if cleaned:
            out.append(cleaned)
    return out


class SceneMemory:
    """Reads and writes the scene layer.

    Kept separate from :class:`~soapbot.memory.store.MemoryStore` because the lifetimes
    differ: the store owns individual memories, this owns the derived view of them. A
    store method that also rebuilt portraits would make every ``add_memory`` pay for a
    summary nobody asked for.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    # ----------------------------------------------------------------- sources
    async def _sample(self, session: Any, scope: str) -> list[MemoryRow]:
        """The bounded evidence window both derived views are built from.

        One helper rather than one query per view: the card and the portrait describe the
        same conversation, and building them from two different windows meant a card that
        listed topics the portrait had never seen.

        Two half-windows, merged. Ordering by importance alone froze the view: a group
        whose 200 highest-importance memories were all old would never sample anything new,
        so the card would describe a conversation the group had moved on from — while
        ``memory_count`` kept climbing. Ordering by recency alone has the opposite failure,
        dropping the few memories that were marked as mattering. Half of the budget each
        way keeps both, and the total is still :data:`CARD_SOURCE_LIMIT`.
        """
        half = CARD_SOURCE_LIMIT // 2
        recent = (
            select(MemoryRow)
            .where(MemoryRow.scope == scope)
            .order_by(MemoryRow.created_at.desc())
            .limit(half)
        )
        important = (
            select(MemoryRow)
            .where(MemoryRow.scope == scope)
            .order_by(MemoryRow.importance.desc(), MemoryRow.created_at.desc())
            .limit(half)
        )
        rows: dict[int, MemoryRow] = {}
        for stmt in (recent, important):
            for row in (await session.execute(stmt)).scalars().all():
                rows.setdefault(row.id, row)
        # Newest first so downstream counters break ties toward what is current.
        return sorted(rows.values(), key=lambda row: row.created_at or 0.0, reverse=True)

    async def _total(self, session: Any, scope: str) -> int:
        """How many memories the scope actually holds.

        Separate from ``len(sample)`` on purpose. The sample is capped so a card stays
        cheap; the *count* is reported to the reader and to ``confidence``, and capping it
        would make a group with 50 000 memories claim to have 200 — a number that is not
        merely stale but wrong, and wrong in the direction that hides how much evidence
        the portrait rests on.
        """
        return int(
            (
                await session.execute(
                    select(func.count()).select_from(MemoryRow).where(MemoryRow.scope == scope)
                )
            ).scalar_one()
        )

    # ------------------------------------------------------------------ cards
    async def build_card(self, scope: str, *, title: str = "") -> SceneCard:
        """Derive a card from the memories in ``scope``.

        Reads at most :data:`CARD_SOURCE_LIMIT` rows. The bound is what keeps this
        affordable on every turn; ``memory_count`` still reports the true total, so the
        card can be both cheap and honest.
        """
        async with self.db.session_factory()() as session:
            rows = await self._sample(session, scope)
            total = await self._total(session, scope)

        card = SceneCard(scope=scope, title=title or scope, memory_count=total)
        if not rows:
            return card

        topic_counter: Counter[str] = Counter()
        person_counter: Counter[str] = Counter()
        for row in rows:
            topic_counter.update(_keywords_of(row))
            if row.subject:
                person_counter[row.subject] += 1

        card.topics = [word for word, _ in topic_counter.most_common(CARD_TOPIC_LIMIT)]
        card.people = [who for who, _ in person_counter.most_common(CARD_PERSON_LIMIT)]
        card.summary = self._summarise_card(card)
        card.updated_at = time.time()
        return card

    @staticmethod
    def _summarise_card(card: SceneCard) -> str:
        """Assemble the card's one-line summary from its own fields.

        No model call. The summary is a restatement of counts that are already on the
        card, which means it cannot say anything the card's other fields do not support —
        the property that makes it safe to inject without review.
        """
        if not card.topics:
            return f"共 {card.memory_count} 条记忆。"
        head = "、".join(card.topics[:3])
        return f"共 {card.memory_count} 条记忆，主要围绕 {head}。"

    async def save_card(self, card: SceneCard) -> None:
        """Persist a card, replacing any previous one for the same scope.

        An upsert rather than select-then-insert. The two-step version had a window
        between the read and the write in which a second writer could insert the same
        scope, and the loser's INSERT then failed on the UNIQUE constraint — a race that
        only appears when two turns for one group overlap, which is exactly what a busy
        group produces. ``ON CONFLICT`` makes "one row per scope" a property of the
        statement instead of a property of the interleaving.
        """
        values = {
            "scope": card.scope,
            "title": card.title,
            "summary": card.summary,
            "topics": "\n".join(card.topics),
            "people": "\n".join(card.people),
            "memory_count": card.memory_count,
            "updated_at": card.updated_at or time.time(),
        }
        async with self.db.write() as session:
            await session.execute(
                sqlite_insert(SceneCardRow)
                .values(**values)
                .on_conflict_do_update(index_elements=["scope"], set_=values)
            )

    async def get_card(self, scope: str) -> SceneCard | None:
        async with self.db.session_factory()() as session:
            row = (
                await session.execute(
                    select(SceneCardRow).where(SceneCardRow.scope == scope)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return SceneCard(
            scope=row.scope,
            title=row.title,
            summary=row.summary,
            topics=[t for t in (row.topics or "").split("\n") if t],
            people=[p for p in (row.people or "").split("\n") if p],
            memory_count=row.memory_count,
            updated_at=row.updated_at,
        )

    # --------------------------------------------------------------- portraits
    async def build_portrait(self, scope: str) -> ScenePortrait:
        """Derive a portrait, or an empty one when there is not enough evidence.

        Returns an *empty* portrait below :data:`PORTRAIT_MIN_MEMORIES` rather than a
        thin one. A portrait that says "this group talks about 什么" after three messages
        is worse than no portrait: it is injected as fact and it is not one.
        """
        async with self.db.session_factory()() as session:
            rows = await self._sample(session, scope)
            total = await self._total(session, scope)

        portrait = ScenePortrait(scope=scope, memory_count=total)
        if total < PORTRAIT_MIN_MEMORIES:
            return portrait

        theme_counter: Counter[str] = Counter()
        question_counter: Counter[str] = Counter()
        question_marks = 0
        for row in rows:
            theme_counter.update(_keywords_of(row))
            content = _clean(row.content or "", _PORTRAIT_SNIPPET)
            if _QUESTION_RE.search(content):
                question_marks += 1
                question_counter[content] += 1

        portrait.themes = [word for word, _ in theme_counter.most_common(CARD_TOPIC_LIMIT)]
        portrait.recurring_questions = [
            text for text, count in question_counter.most_common(3) if count >= 2
        ]
        portrait.tone = self._infer_tone(question_marks, len(rows))
        portrait.headline = (
            f"围绕 {'、'.join(portrait.themes[:3])} 的对话"
            if portrait.themes
            else f"{total} 条记忆"
        )
        # Confidence describes the evidence the *portrait* rests on, which is the sample —
        # not the size of the scope. Measuring it against the total made it a restatement
        # of "how big is this group": a scope with 50 000 memories reported ~0.999 while
        # the portrait itself was still built from the same 200 rows, so the number rose
        # without the portrait getting any better. Saturating at the sample cap is correct
        # and intended: past CARD_SOURCE_LIMIT rows the portrait genuinely cannot improve,
        # because it never sees more.
        portrait.confidence = round(min(1.0, len(rows) / (len(rows) + 40.0)), 3)
        portrait.updated_at = time.time()
        return portrait

    @staticmethod
    def _infer_tone(questions: int, total: int) -> str:
        """Classify the register from the share of questions.

        Three buckets, not a spectrum: the caller injects this as a hint, and "42% question
        density" is not a hint anyone can act on.
        """
        if total == 0:
            return ""
        share = questions / total
        if share >= 0.4:
            return "提问为主，成员多在寻求答案"
        if share >= 0.15:
            return "问答与闲聊混合"
        return "以陈述和闲聊为主"

    async def save_portrait(self, portrait: ScenePortrait) -> None:
        """Persist a portrait, replacing any previous one for the same scope.

        Upsert for the same reason as :meth:`save_card`: two turns for one group can
        finish their refresh at the same moment, and the loser of a select-then-insert
        race would crash on the UNIQUE constraint instead of simply overwriting.
        """
        values = {
            "scope": portrait.scope,
            "headline": portrait.headline,
            "themes": "\n".join(portrait.themes),
            "tone": portrait.tone,
            "recurring_questions": "\n".join(portrait.recurring_questions),
            "memory_count": portrait.memory_count,
            "confidence": portrait.confidence,
            "updated_at": portrait.updated_at or time.time(),
        }
        async with self.db.write() as session:
            await session.execute(
                sqlite_insert(ScenePortraitRow)
                .values(**values)
                .on_conflict_do_update(index_elements=["scope"], set_=values)
            )

    async def get_portrait(self, scope: str) -> ScenePortrait | None:
        async with self.db.session_factory()() as session:
            row = (
                await session.execute(
                    select(ScenePortraitRow).where(ScenePortraitRow.scope == scope)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return ScenePortrait(
            scope=row.scope,
            headline=row.headline,
            themes=[t for t in (row.themes or "").split("\n") if t],
            tone=row.tone,
            recurring_questions=[
                q for q in (row.recurring_questions or "").split("\n") if q
            ],
            memory_count=row.memory_count,
            confidence=row.confidence,
            updated_at=row.updated_at,
        )

    # ------------------------------------------------------------------- links
    async def link(self, source_id: int, target_id: int, kind: str, weight: float = 1.0) -> None:
        """Record an edge, ignoring duplicates.

        ``kind`` is validated against :data:`LINK_KINDS` rather than stored as given: an
        unvalidated vocabulary is one nobody can query later, and the failure is silent —
        the edge exists, it just never matches a reader's filter.

        Both endpoints must exist and share a scope. Without that check an edge could join
        a memory in one group to a memory in another, and ``neighbours`` would then hand a
        caller ids from a scope it is not allowed to read — the edge table has no scope
        column of its own, so this is the only place the invariant can be enforced.
        """
        if kind not in LINK_KINDS:
            raise ValueError(f"unknown link kind {kind!r}; expected one of {sorted(LINK_KINDS)}")
        if source_id == target_id:
            # A self-link carries no information and would make "related memories"
            # return the memory itself, which reads as a bug to anyone who sees it.
            return
        if not math.isfinite(weight) or weight < 0:
            # NaN survives every comparison (``NaN > 0`` is False, ``NaN < 0`` is False),
            # so it would slip past a plain range check and then poison the ordering:
            # ``max(NaN, x)`` is NaN in SQLite, permanently pinning the edge at a weight
            # that sorts arbitrarily.
            raise ValueError(f"link weight must be a finite non-negative number, got {weight!r}")

        async with self.db.session_factory()() as session:
            scopes = dict(
                (
                    await session.execute(
                        select(MemoryRow.id, MemoryRow.scope).where(
                            MemoryRow.id.in_((source_id, target_id))
                        )
                    )
                ).all()
            )
        if len(scopes) != 2:
            # One or both endpoints are gone. Writing the edge anyway would create a
            # dangling reference that ``neighbours`` resolves to nothing.
            return
        if len(set(scopes.values())) != 1:
            logger.warning(
                "refusing cross-scope link %s -> %s (%s vs %s)",
                source_id,
                target_id,
                scopes.get(source_id),
                scopes.get(target_id),
            )
            return

        stmt = sqlite_insert(SceneLinkRow).values(
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            weight=weight,
            created_at=time.time(),
        )
        # ``max(existing, new)`` rather than ``new``: the weight is evidence strength, and
        # a later weaker observation must not downgrade a stronger earlier one. The
        # upsert also removes the select-then-insert race — the unique index is the
        # arbiter, so two writers recording the same edge both succeed.
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "target_id", "kind"],
            set_={"weight": func.max(SceneLinkRow.weight, stmt.excluded.weight)},
        )
        async with self.db.write() as session:
            await session.execute(stmt)

    async def neighbours(self, memory_id: int, *, kind: str = "", limit: int = 5) -> list[int]:
        """Memory ids linked to this one, strongest first.

        Both directions: a link written as ``a -> b`` means "a is about the same subject
        as b", which is symmetric in practice even though the row is not. Returning only
        outgoing edges would make recall depend on which memory happened to be written
        first.

        The limit is applied in SQL, not after fetching. A memory that has accumulated
        thousands of edges would otherwise pull every one of them into Python to return
        five — the same cost as having no limit at all, paid on the recall path.
        """
        if limit <= 0:
            return []
        out_edges = select(
            SceneLinkRow.target_id.label("other_id"),
            SceneLinkRow.weight.label("weight"),
        ).where(SceneLinkRow.source_id == memory_id)
        in_edges = select(
            SceneLinkRow.source_id.label("other_id"),
            SceneLinkRow.weight.label("weight"),
        ).where(SceneLinkRow.target_id == memory_id)
        if kind:
            out_edges = out_edges.where(SceneLinkRow.kind == kind)
            in_edges = in_edges.where(SceneLinkRow.kind == kind)
        edges = union_all(out_edges, in_edges).subquery()
        stmt = (
            select(edges.c.other_id)
            # A memory can reach the same neighbour through two different edges (out and
            # in, or two kinds); grouping collapses them so the caller gets ids, not
            # duplicates it would have to filter.
            .where(edges.c.other_id != memory_id)
            .group_by(edges.c.other_id)
            .order_by(func.max(edges.c.weight).desc(), edges.c.other_id)
            .limit(limit)
        )
        async with self.db.session_factory()() as session:
            return list((await session.execute(stmt)).scalars().all())

    async def unlink_all(self, memory_id: int) -> int:
        """Drop every edge touching a memory. Called when the memory is deleted.

        Without this, deleting a memory leaves edges pointing at a row that no longer
        exists, and ``neighbours`` returns ids that resolve to nothing — a dangling
        reference that looks like data loss to whoever hits it.
        """
        async with self.db.write() as session:
            result = await session.execute(
                delete(SceneLinkRow).where(
                    (SceneLinkRow.source_id == memory_id)
                    | (SceneLinkRow.target_id == memory_id)
                )
            )
            return int(result.rowcount or 0)

    # ------------------------------------------------------------------ upkeep
    async def list_scenes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Every scope that holds memories, with its stored card if one exists.

        The panel needs an entry point that is not "type a session key": before this, the
        only way to see a card was to already know which conversation to ask about, which
        meant the feature was invisible to anyone who had not read the source.

        Driven by ``memories`` rather than by ``scene_cards``, because a scope with
        memories and no card is the interesting case — it is a conversation the bot has
        learned from but never summarised, and it should be offered for a rebuild rather
        than hidden. A card with no memories behind it would be the opposite: a summary of
        evidence that no longer exists, which ``refresh`` already deletes.
        """
        async with self.db.session_factory()() as session:
            counts = (
                await session.execute(
                    select(MemoryRow.scope, func.count(MemoryRow.id))
                    .group_by(MemoryRow.scope)
                    .order_by(func.count(MemoryRow.id).desc())
                    .limit(limit)
                )
            ).all()
            if not counts:
                return []
            scopes = [row[0] for row in counts]
            cards = {
                row.scope: row
                for row in (
                    await session.execute(
                        select(SceneCardRow).where(SceneCardRow.scope.in_(scopes))
                    )
                )
                .scalars()
                .all()
            }
            portraits = {
                row.scope: row
                for row in (
                    await session.execute(
                        select(ScenePortraitRow).where(ScenePortraitRow.scope.in_(scopes))
                    )
                )
                .scalars()
                .all()
            }

        out: list[dict[str, Any]] = []
        for scope, count in counts:
            card = cards.get(scope)
            portrait = portraits.get(scope)
            out.append(
                {
                    "scope": scope,
                    "memory_count": int(count),
                    "title": card.title if card is not None else "",
                    "summary": card.summary if card is not None else "",
                    "has_card": card is not None,
                    "has_portrait": portrait is not None,
                    "portrait_confidence": portrait.confidence if portrait is not None else 0.0,
                    "updated_at": card.updated_at if card is not None else 0.0,
                }
            )
        return out

    async def evidence(self, scope: str, *, limit: int = CARD_SOURCE_LIMIT) -> list[tuple[int, str, str]]:
        """``(id, content, keywords)`` triples for one scope.

        The shape :meth:`soapbot.memory.skills.SkillForge.candidates` expects. Kept here
        rather than in the API module so the sampling rule is the same one the card uses:
        a skill distilled from a different window than the card would describe a
        conversation the card does not mention.
        """
        async with self.db.session_factory()() as session:
            rows = await self._sample(session, scope)
        return [(row.id, row.content or "", row.keywords or "") for row in rows[:limit]]

    async def refresh(self, scope: str, *, title: str = "") -> tuple[SceneCard, ScenePortrait]:
        """Rebuild and persist both views for a scope.

        This is the "write back to the scene layer" step: after new memories land, the
        derived views are recomputed and stored, so the next turn reads a card instead of
        recomputing one.
        """
        card = await self.build_card(scope, title=title)
        portrait = await self.build_portrait(scope)
        await self.save_card(card)
        if portrait.memory_count >= PORTRAIT_MIN_MEMORIES:
            await self.save_portrait(portrait)
        else:
            # Drop a portrait that no longer has enough evidence behind it. Memories can be
            # deleted, and leaving the old portrait in place would keep injecting a summary
            # of rows that no longer exist — the one case where a stale derived view is
            # actively wrong rather than merely old.
            await self.drop_portrait(scope)
        return card, portrait

    async def drop_portrait(self, scope: str) -> bool:
        """Remove a stored portrait. Returns whether one existed."""
        async with self.db.write() as session:
            result = await session.execute(
                delete(ScenePortraitRow).where(ScenePortraitRow.scope == scope)
            )
            return bool(result.rowcount)
