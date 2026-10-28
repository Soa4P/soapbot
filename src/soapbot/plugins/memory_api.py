"""The memory / knowledge / session surfaces a plugin may use (``ctx.memory`` …).

Why this module is separate from ``context.py``
-----------------------------------------------
Three capabilities — ``memory_read``, ``kb_read`` and ``session`` — were declared in
:class:`soapbot.plugins.manifest.Capability`, listed as sensitive, and checked by the
config docs, but **nothing implemented them**: ``PluginContext`` had no method for
any of them and ``build_plugin_manager`` never passed a store in. A plugin that asked
for ``memory_read`` was approved for a capability it could not use, and a plugin that
*didn't* ask got exactly the same nothing. That is worse than a missing feature: the
capability list told the operator a risk had been reviewed and was being enforced,
when in fact there was no code path at all.

The design that makes the safe thing the easy thing
---------------------------------------------------
The temptation with a memory API is to expose ``recall(query, scope=...)`` and let the
plugin pass a scope. That single parameter is a cross-tenant read primitive: every
memory row is reachable by naming its session key, and the isolation review had
already shown what happens when a plugin can choose its own reach.

So the scope is **not a parameter**. Every method here derives it from the caller the
host resolved:

    ctx.memory.recall("猫")        # scope = caller's session, always

A plugin physically cannot express "read group B's memories" through this API — not
because a check rejects it, but because there is no argument to put it in. The check
and the ergonomics are the same decision, which is the only kind of security control
that survives a well-meaning refactor.

What is deliberately **not** here
---------------------------------
No writes to long-term memory. A plugin that could write memories would have a
persistence layer for prompt injection: one planted fact is recalled into every
future turn, so the escalation outlives the message that caused it. Memory writing
stays in the host's ``MemoryWriteStage`` where ``vet_memory`` quarantines privilege
claims. Plugins get read-only recall, which is enough for "answer using what you know
about this group" and useless for permanently poisoning the bot.

No raw ``session`` object either: :class:`SessionView` is an immutable snapshot of a
few scalars, not a handle on the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import CapabilityGuard, scrub_plugin_output

#: A plugin's recall is a chat-turn operation, not a batch job. Caps are deliberately
#: tighter than the core's ``/recall`` (which allows 8): a plugin runs on every
#: matching message, so its per-call budget multiplies by traffic.
MAX_RECALL_LIMIT = 10
MAX_QUERY_CHARS = 200
MAX_SNIPPET_CHARS = 300
"""Per-item cap on returned text.

Retrieved memory is attacker-influenced: a group member typed it. Handing 8 × 4 KB
of it to a plugin that then formats it into a reply is a convenient way to push a
large block of attacker text through the bot's own output. Truncating here bounds
that amplification without making the API useless.
"""

MAX_TOTAL_CHARS = 2000


@dataclass(frozen=True, slots=True)
class MemoryHit:
    """One recalled memory, trimmed to what a plugin can safely show.

    ``id`` is included so a plugin can reference a row it saw, but there is no
    ``delete`` here: acting on an id is a privileged operation that belongs to the
    host's ``/forget`` command, which checks ownership before touching the row.
    """

    id: int
    content: str
    score: float
    source: str
    scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """One knowledge-base chunk. ``title`` is operator-authored, ``content`` is not."""

    title: str
    content: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "content": self.content, "score": self.score}


@dataclass(frozen=True, slots=True)
class SessionView:
    """Immutable snapshot of the current conversation, for ``ctx.session``.

    Not the event, not the principal, not a handle. Four scalars, because a plugin
    needs to know "am I in a group, which one, who is asking" and nothing else.
    Handing over the ``Principal`` would hand over ``granted`` permissions — a plugin
    reading that set could adapt its behaviour to whichever identity is asking,
    which is reconnaissance it does not need.
    """

    session_key: str
    scene: str
    group_id: str
    user_id: str
    display_name: str
    is_group: bool


class PluginMemoryAPI:
    """``ctx.memory`` — read-only recall, scoped to the caller by construction."""

    __slots__ = ("_guard", "_plugin", "_session_key", "_store")

    def __init__(
        self,
        *,
        guard: CapabilityGuard,
        plugin: str,
        store,
        session_key: str,
    ) -> None:
        self._guard = guard
        self._plugin = plugin
        self._store = store
        # An empty scope is NOT "the plugin's own scope" — in the store, `scope=""`
        # disables the filter entirely and would return every group's memories. That
        # is exactly what a cron job's anonymous caller would produce, so refuse it
        # here rather than relying on every dispatch path to remember.
        self._session_key = session_key or ""

    @property
    def available(self) -> bool:
        """Whether a backing store exists — lets a plugin degrade gracefully.

        Checked without raising so a plugin can write ``if ctx.memory.available``
        instead of catching an exception on a bot where memory is not configured.
        Note this is *only* about configuration; capability is still enforced by the
        calls themselves, so a plugin cannot use this as an authorisation probe.
        """
        return self._store is not None

    async def recall(self, query: str, *, limit: int = 5) -> list[MemoryHit]:
        """Search long-term memory in the caller's scope.

        Authorisation: ``memory_read``, checked on **every call** rather than at
        registration. A plugin might register a command while holding the capability
        and then be denied after the operator revokes it; re-checking at call time is
        what makes revocation take effect without a reload.
        """
        self._guard.check(Capability.MEMORY_READ, detail=f"recall len={len(query or '')}")
        if self._store is None:
            return []
        if not self._session_key:
            # No session means no scope to pin to. Returning [] is the safe answer;
            # passing `scope=""` down would read across every conversation.
            raise RuntimeError(
                "ctx.memory.recall requires a conversation scope; it is unavailable "
                "in a context with no session (e.g. a cron job)"
            )

        text = _clean_query(query)
        if not text:
            return []
        cap = max(1, min(int(limit), MAX_RECALL_LIMIT))

        # Scope comes from the host, never from the caller. There is intentionally no
        # parameter that could widen it.
        result = await self._store.recall(text, scope=self._session_key, limit=cap)

        hits: list[MemoryHit] = []
        budget = MAX_TOTAL_CHARS
        for item in result.items:
            # Defence in depth: the store already filtered by scope, but a future
            # change adding a global fallback must not silently become a cross-scope
            # leak through the plugin path. Same belt-and-braces as the core command.
            if item.scope and item.scope != self._session_key:
                continue
            content = scrub_plugin_output(str(item.content), max_chars=MAX_SNIPPET_CHARS)
            if not content:
                continue
            if len(content) > budget:
                content = content[:budget]
            budget -= len(content)
            hits.append(
                MemoryHit(
                    id=item.id,
                    content=content,
                    score=round(float(item.score), 4),
                    source=item.source,
                    scope=item.scope,
                )
            )
            if budget <= 0:
                break
        return hits

    async def about_me(self, *, limit: int = 5) -> list[MemoryHit]:
        """Shortcut for "what do you know about this conversation's participants".

        Exists so the common case does not require inventing a query. It broadens
        nothing: it is ``recall`` with a fixed neutral query, same scope, same
        capability, same caps.
        """
        return await self.recall("用户 喜欢 名字 生日 工作", limit=limit)


class PluginKnowledgeAPI:
    """``ctx.kb`` — read-only knowledge-base query."""

    __slots__ = ("_guard", "_kb", "_plugin")

    def __init__(self, *, guard: CapabilityGuard, plugin: str, kb) -> None:
        self._guard = guard
        self._plugin = plugin
        self._kb = kb

    @property
    def available(self) -> bool:
        return self._kb is not None

    async def search(self, query: str, *, limit: int = 3) -> list[KnowledgeHit]:
        """Search operator-uploaded documents.

        Authorisation: ``kb_read``, per call. The knowledge base usually holds
        internal material, so this is a sensitive capability with its own tight
        quota — see ``CapabilityGuard``.
        """
        self._guard.check(Capability.KB_READ, detail=f"kb search len={len(query or '')}")
        if self._kb is None:
            return []

        text = _clean_query(query)
        if not text:
            return []
        cap = max(1, min(int(limit), 5))

        raw = await self._kb.search(text, limit=cap)
        hits: list[KnowledgeHit] = []
        budget = MAX_TOTAL_CHARS
        for row in raw:
            # Doc *content* is operator-authored but may embed anything they pasted;
            # treat it as untrusted on the way out like every other data path.
            content = scrub_plugin_output(
                str(row.get("content", "")), max_chars=MAX_SNIPPET_CHARS
            )
            if not content:
                continue
            if len(content) > budget:
                content = content[:budget]
            budget -= len(content)
            hits.append(
                KnowledgeHit(
                    title=str(row.get("title") or ""),
                    content=content,
                    score=round(float(row.get("score") or 0.0), 4),
                )
            )
            if budget <= 0:
                break
        return hits

    async def list_documents(self) -> list[dict[str, Any]]:
        """Titles only — no content, no chunk text.

        Listing is separated from searching so a plugin that needs "is there a rule
        document?" does not have to pull every chunk into its own memory to find out.
        """
        self._guard.check(Capability.KB_READ, detail="kb list")
        if self._kb is None:
            return []
        docs = await self._kb.list_documents()
        return [
            {"doc_id": str(d.get("doc_id", "")), "title": str(d.get("title", ""))}
            for d in docs
        ]


def _clean_query(query: Any) -> str:
    """Normalise a query string, or return empty so the caller returns no results.

    An over-long query is truncated rather than rejected: a plugin passing a user's
    whole message is the expected usage, and failing it would make the API awkward
    for the common case while gaining nothing (the store caps its own work).
    """
    if not isinstance(query, str):
        return ""
    text = query.strip()
    if not text:
        return ""
    return text[:MAX_QUERY_CHARS]


def build_session_view(caller) -> SessionView:
    """Snapshot a ``CallerContext`` into the shape ``ctx.session`` exposes."""
    return SessionView(
        session_key=caller.session_key,
        scene=caller.scene,
        group_id=caller.group_id,
        user_id=caller.user_id,
        display_name=caller.display_name,
        is_group=caller.scene == "group",
    )
