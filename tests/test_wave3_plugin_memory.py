"""Wave 3 exposed to plugins: ctx.memory / ctx.kb / ctx.session.

These are the same Wave 3 stores the core uses; the tests below check the *plugin
surface* on top of them, which is where the authorisation risk lives.

Background — the defect this closes
-----------------------------------
``memory_read``, ``kb_read`` and ``session`` were declared in ``Capability``, listed
as sensitive in the guard's quota table, and documented as operator-approvable — but
``PluginContext`` had no method for any of them and ``build_plugin_manager`` never
passed a store in. A plugin approved for ``memory_read`` could not recall anything;
one that never asked got the same nothing. The capability list implied a reviewed
and enforced risk when in fact no code path existed. These tests pin the real
behaviour now that the path exists.

The central claims under test:

1. ``ctx.memory`` / ``ctx.kb`` / ``ctx.session`` **cannot express** a cross-session
   read — there is no scope parameter anywhere in the API;
2. the capability is re-checked on **every call**, so revocation takes effect
   without a plugin reload.
"""

from __future__ import annotations

import pytest

from soapbot.memory.store import MemoryItem, RecallResult
from soapbot.plugins.context import CallerContext, PluginContext, bind_caller
from soapbot.plugins.manifest import Capability
from soapbot.plugins.memory_api import (
    MAX_QUERY_CHARS,
    MAX_RECALL_LIMIT,
    MAX_SNIPPET_CHARS,
    MAX_TOTAL_CHARS,
    PluginKnowledgeAPI,
    PluginMemoryAPI,
    build_session_view,
)
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGrant, CapabilityGuard
from soapbot.security.audit import AuditLog

# --------------------------------------------------------------------- fixtures


def _guard(caps: set[Capability], plugin: str = "p") -> CapabilityGuard:
    return CapabilityGuard(
        CapabilityGrant(plugin=plugin, declared=frozenset(caps), approved=frozenset(caps)),
        audit=AuditLog(),
    )


def _caller(session_key: str = "onebot11:group:111", **kw) -> CallerContext:
    return CallerContext(
        user_id=kw.get("user_id", "u1"),
        display_name=kw.get("display_name", "小明"),
        role=kw.get("role", "user"),
        session_key=session_key,
        scene=kw.get("scene", "group"),
        group_id=kw.get("group_id", "111"),
    )


class FakeStore:
    """Stands in for ``MemoryStore``. Records the scope every call was made with.

    ``seen_scopes`` is the point of the whole file: if a scope ever arrives that the
    host did not derive from the caller, the fake will show it.
    """

    def __init__(self, items: list[MemoryItem] | None = None) -> None:
        self.items = items or []
        self.seen_scopes: list[str] = []
        self.seen_limits: list[int] = []

    async def recall(self, query: str, *, scope: str = "", limit: int = 8, layers=None):
        self.seen_scopes.append(scope)
        self.seen_limits.append(limit)
        return RecallResult(items=self.items[:limit], query=query)


class FakeKB:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.seen_limits: list[int] = []

    async def search(self, query: str, *, limit: int = 5):
        self.seen_limits.append(limit)
        return self.rows[:limit]

    async def list_documents(self):
        return [{"doc_id": "d1", "title": "群规", "content": "长正文不该出现在列表里"}]


def _items(scope: str = "onebot11:group:111", n: int = 1) -> list[MemoryItem]:
    return [
        MemoryItem(
            id=i + 1, layer="episodic", content=f"记忆{i + 1}", scope=scope,
            score=0.9, source="both",
        )
        for i in range(n)
    ]


# ================================================== authorisation: the core claim


async def test_memory_recall_denied_without_capability() -> None:
    """No ``memory_read`` grant -> raise, and the store is never touched."""
    store = FakeStore(_items())
    api = PluginMemoryAPI(
        guard=_guard({Capability.COMMAND}),
        plugin="p",
        store=store,
        session_key="onebot11:group:111",
    )
    with pytest.raises(CapabilityDeniedError):
        await api.recall("猫")
    assert store.seen_scopes == [], "store must not be queried before the check"


async def test_kb_search_denied_without_capability() -> None:
    kb = FakeKB([{"title": "t", "content": "c", "score": 1.0}])
    api = PluginKnowledgeAPI(guard=_guard({Capability.MEMORY_READ}), plugin="p", kb=kb)
    with pytest.raises(CapabilityDeniedError):
        await api.search("群规")
    assert kb.seen_limits == []


async def test_session_view_denied_without_capability() -> None:
    ctx = PluginContext(plugin="p", guard=_guard({Capability.MEMORY_READ}))
    with bind_caller(_caller()), pytest.raises(CapabilityDeniedError):
        _ = ctx.session


async def test_memory_and_session_are_separate_grants() -> None:
    """Holding ``memory_read`` must not imply ``session``, and vice versa.

    Bundling them would be convenient and wrong: "which group am I in" and "what did
    this group say" are different disclosures.
    """
    ctx = PluginContext(plugin="p", guard=_guard({Capability.SESSION}))
    with bind_caller(_caller()):
        assert ctx.session.is_group is True                     # session works
        with pytest.raises(CapabilityDeniedError):
            await ctx.memory.recall("猫")                        # memory does not


async def test_revocation_takes_effect_without_reload() -> None:
    """The guard is consulted per call, so revoking mid-life stops the next call."""
    store = FakeStore(_items())
    guard = _guard({Capability.MEMORY_READ})
    api = PluginMemoryAPI(
        guard=guard, plugin="p", store=store, session_key="onebot11:group:111"
    )
    assert await api.recall("猫")

    # Revocation cannot be simulated by writing ``guard.grant``: the guard is sealed
    # against exactly that (isolation review, defect I1). The real path is that the
    # loader rebuilds the guard with an empty approved set on re-approve, so build a
    # second API bound to such a guard and show the identical call now fails.
    revoked = PluginMemoryAPI(
        guard=CapabilityGuard(
            CapabilityGrant(
                plugin="p",
                declared=frozenset({Capability.MEMORY_READ}),
                approved=frozenset(),
            ),
            audit=AuditLog(),
        ),
        plugin="p",
        store=store,
        session_key="onebot11:group:111",
    )
    with pytest.raises(CapabilityDeniedError):
        await revoked.recall("猫")


async def test_undeclared_capability_is_still_refused() -> None:
    """Approved without declared must not work — the two-gate model still applies."""
    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="p",
            declared=frozenset(),                              # never declared
            approved=frozenset({Capability.MEMORY_READ}),      # but operator approved
        ),
        audit=AuditLog(),
    )
    api = PluginMemoryAPI(
        guard=guard, plugin="p", store=FakeStore(_items()), session_key="onebot11:group:111"
    )
    with pytest.raises(CapabilityDeniedError):
        await api.recall("猫")


# ================================================== scope cannot be widened


async def test_scope_is_the_callers_session() -> None:
    store = FakeStore(_items())
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}),
        plugin="p",
        store=store,
        session_key="onebot11:group:111",
    )
    await api.recall("猫")
    assert store.seen_scopes == ["onebot11:group:111"]


async def test_recall_takes_no_scope_argument() -> None:
    """The strongest guarantee is that the argument does not exist.

    If someone later adds ``scope=`` for convenience, this test fails and forces the
    conversation — which is the entire value of writing it down.
    """
    import inspect

    sig = inspect.signature(PluginMemoryAPI.recall)
    assert "scope" not in sig.parameters
    # ``query`` and ``limit`` are the only knobs, and neither widens reach.
    assert set(sig.parameters) == {"self", "query", "limit"}


async def test_cross_scope_items_are_dropped_defence_in_depth() -> None:
    """Even if the store returned another scope's row, the API filters it.

    Belt and braces: today the store filters by scope, but a future "global
    fallback" for better recall must not silently become a plugin-side leak.
    """
    leaked = [
        MemoryItem(id=1, layer="episodic", content="本群的", scope="onebot11:group:111", score=0.9),
        MemoryItem(
            id=2, layer="episodic", content="别的群的秘密",
            scope="onebot11:group:999", score=0.8,
        ),
    ]
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}),
        plugin="p",
        store=FakeStore(leaked),
        session_key="onebot11:group:111",
    )
    hits = await api.recall("秘密")
    assert [h.content for h in hits] == ["本群的"]


async def test_empty_scope_refuses_instead_of_reading_everything() -> None:
    """``scope=""`` means "no filter" in the store — it must never reach it.

    A cron job's anonymous caller produces an empty session key. Passing that down
    would return every group's memories to a background job.
    """
    store = FakeStore(_items())
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=store, session_key=""
    )
    with pytest.raises(RuntimeError, match="scope"):
        await api.recall("猫")
    assert store.seen_scopes == []


# ================================================== caller binding


async def test_memory_outside_invocation_raises() -> None:
    """Using ``ctx.memory`` in setup / a bare task fails loudly, never guesses."""
    ctx = PluginContext(plugin="p", guard=_guard({Capability.MEMORY_READ}))
    with pytest.raises(RuntimeError, match="outside a plugin invocation"):
        _ = ctx.memory


async def test_session_outside_invocation_raises() -> None:
    ctx = PluginContext(plugin="p", guard=_guard({Capability.SESSION}))
    with pytest.raises(RuntimeError, match="outside a plugin invocation"):
        _ = ctx.session


async def test_bind_caller_resets_on_exception() -> None:
    """A failing handler must not leave its caller bound for the next task."""
    ctx = PluginContext(plugin="p", guard=_guard({Capability.SESSION}))
    with pytest.raises(ValueError), bind_caller(_caller()):
        raise ValueError("boom")
    with pytest.raises(RuntimeError, match="outside a plugin invocation"):
        _ = ctx.session


async def test_concurrent_callers_do_not_mix() -> None:
    """Two conversations on separate tasks must not see each other's scope.

    This is why the caller lives in a ContextVar rather than on the context object:
    the context object is shared by every call of one plugin.
    """
    import asyncio

    store = FakeStore(_items())
    ctx = PluginContext(plugin="p", guard=_guard({Capability.MEMORY_READ}), memory=store)

    async def one(session_key: str) -> None:
        with bind_caller(_caller(session_key=session_key)):
            await asyncio.sleep(0)  # force interleaving
            await ctx.memory.recall("猫")
            await asyncio.sleep(0)

    await asyncio.gather(one("onebot11:group:AAA"), one("onebot11:group:BBB"))
    assert sorted(store.seen_scopes) == ["onebot11:group:AAA", "onebot11:group:BBB"]


# ================================================== caps and output hygiene


async def test_limit_is_clamped() -> None:
    store = FakeStore(_items(n=50))
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=store,
        session_key="onebot11:group:111",
    )
    await api.recall("猫", limit=9999)
    assert store.seen_limits == [MAX_RECALL_LIMIT]


async def test_query_is_truncated_not_rejected() -> None:
    """A plugin passing a whole message should work, not explode."""
    store = FakeStore(_items())
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=store,
        session_key="onebot11:group:111",
    )
    assert await api.recall("字" * 5000)
    assert store.seen_scopes == ["onebot11:group:111"]


async def test_empty_query_returns_nothing_without_querying() -> None:
    store = FakeStore(_items())
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=store,
        session_key="onebot11:group:111",
    )
    assert await api.recall("   ") == []
    assert store.seen_scopes == []


async def test_non_string_query_is_rejected_quietly() -> None:
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=FakeStore(_items()),
        session_key="onebot11:group:111",
    )
    assert await api.recall(None) == []  # type: ignore[arg-type]


async def test_snippet_is_truncated() -> None:
    long = [
        MemoryItem(
            id=1, layer="episodic", content="长" * 5000,
            scope="onebot11:group:111", score=1.0,
        )
    ]
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=FakeStore(long),
        session_key="onebot11:group:111",
    )
    hits = await api.recall("长")
    # ``scrub_plugin_output`` truncates and appends an ellipsis, so the result can be
    # one codepoint over the cap. Assert the bound, not an exact length: pinning the
    # exact number would break on any change to the scrubber's marker.
    assert len(hits[0].content) <= MAX_SNIPPET_CHARS + 1


async def test_total_output_is_budgeted() -> None:
    many = [
        MemoryItem(
            id=i, layer="episodic", content="字" * MAX_SNIPPET_CHARS,
            scope="onebot11:group:111", score=1.0,
        )
        for i in range(10)
    ]
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=FakeStore(many),
        session_key="onebot11:group:111",
    )
    hits = await api.recall("字", limit=10)
    assert 0 < sum(len(h.content) for h in hits) <= MAX_TOTAL_CHARS + MAX_SNIPPET_CHARS


async def test_markup_in_recalled_memory_is_neutralised() -> None:
    """Recalled text was typed by group members; it is attacker-controlled."""
    hostile = [
        MemoryItem(
            id=1,
            layer="episodic",
            content='<a href="javascript:alert(1)">点我</a>',
            scope="onebot11:group:111",
            score=1.0,
        )
    ]
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=FakeStore(hostile),
        session_key="onebot11:group:111",
    )
    hits = await api.recall("点")
    assert "<" not in hits[0].content
    assert "javascript:" not in hits[0].content


async def test_memory_hit_dict_omits_scope() -> None:
    """``to_dict`` feeds prompts and cards, so it omits the internal session key."""
    api = PluginMemoryAPI(
        guard=_guard({Capability.MEMORY_READ}), plugin="p", store=FakeStore(_items()),
        session_key="onebot11:group:111",
    )
    hit = (await api.recall("猫"))[0]
    assert "scope" not in hit.to_dict()
    assert set(hit.to_dict()) == {"id", "content", "score", "source"}


# ================================================== graceful degradation


async def test_available_false_when_store_missing() -> None:
    """A bot with no memory configured should not make plugins crash."""
    ctx = PluginContext(
        plugin="p", guard=_guard({Capability.MEMORY_READ, Capability.KB_READ})
    )
    with bind_caller(_caller()):
        assert ctx.memory.available is False
        assert ctx.kb.available is False
        assert await ctx.memory.recall("猫") == []
        assert await ctx.kb.search("群规") == []


async def test_unavailable_store_still_requires_capability() -> None:
    """An absent store must not become a way around the check.

    Otherwise a plugin could probe authorisation by observing whether the empty
    result raises.
    """
    ctx = PluginContext(plugin="p", guard=_guard(set()))
    with bind_caller(_caller()), pytest.raises(CapabilityDeniedError):
        await ctx.memory.recall("猫")


# ================================================== kb surface


async def test_kb_list_documents_returns_titles_only() -> None:
    api = PluginKnowledgeAPI(guard=_guard({Capability.KB_READ}), plugin="p", kb=FakeKB())
    docs = await api.list_documents()
    assert docs == [{"doc_id": "d1", "title": "群规"}]
    assert all("content" not in d for d in docs)


async def test_kb_limit_is_clamped_to_five() -> None:
    kb = FakeKB([{"title": f"t{i}", "content": "c", "score": 1.0} for i in range(20)])
    api = PluginKnowledgeAPI(guard=_guard({Capability.KB_READ}), plugin="p", kb=kb)
    await api.search("x", limit=99)
    assert kb.seen_limits == [5]


async def test_kb_list_also_requires_capability() -> None:
    api = PluginKnowledgeAPI(guard=_guard(set()), plugin="p", kb=FakeKB())
    with pytest.raises(CapabilityDeniedError):
        await api.list_documents()


# ================================================== session view shape


def test_session_view_exposes_scalars_only() -> None:
    view = build_session_view(_caller())
    assert view.session_key and view.group_id and view.user_id
    assert view.is_group is True
    # No principal, no permissions, no event, no adapter.
    for forbidden in ("granted", "principal", "event", "adapter", "bot"):
        assert not hasattr(view, forbidden)


def test_session_view_is_immutable() -> None:
    from dataclasses import FrozenInstanceError

    view = build_session_view(_caller())
    with pytest.raises(FrozenInstanceError):
        view.group_id = "999"


def test_private_session_is_not_group() -> None:
    view = build_session_view(_caller(session_key="onebot11:private:u1", scene="private"))
    assert view.is_group is False


def test_query_cap_constant_is_sane() -> None:
    """Guards against someone setting the cap to 0 (disables the API) or huge."""
    assert 50 <= MAX_QUERY_CHARS <= 2000
    assert 1 <= MAX_RECALL_LIMIT <= 20
