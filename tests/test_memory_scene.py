"""The scene layer: index cards, portraits, links, and skills.

The behaviour under test is not "does it store a row". It is the two properties that make
the layer worth having at all:

* **Bounded.** A card is injected on every turn, so its cost must not grow with the size
  of the conversation. A group with 50 000 memories and a group with 20 must both produce
  a card of the same shape.
* **Derived, not invented.** Every field on a card or a portrait has to be traceable to
  rows that exist. Nothing here calls a model, and these tests exist partly to keep it
  that way.
"""

from __future__ import annotations

import asyncio

import pytest

from soapbot.memory.db import Database, reset_database
from soapbot.memory.scene import (
    CARD_SOURCE_LIMIT,
    CARD_TOPIC_LIMIT,
    LINK_KINDS,
    PORTRAIT_MIN_MEMORIES,
    SceneMemory,
)
from soapbot.memory.skills import MIN_SUPPORT, SkillForge
from soapbot.memory.store import MemoryLayer, MemoryStore


@pytest.fixture
async def db(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'scene.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


async def _seed(store: MemoryStore, scope: str, count: int, *, text: str = "部署 服务器") -> list[int]:
    """Store ``count`` memories and return their ids."""
    ids: list[int] = []
    for index in range(count):
        ids.append(
            await store.add_memory(
                content=f"{text} 第{index}条",
                layer=MemoryLayer.SEMANTIC,
                scope=scope,
                embed=False,
            )
        )
    return ids


# ------------------------------------------------------------------ cards


@pytest.mark.asyncio
async def test_a_card_summarises_the_scope_without_a_model(db: Database) -> None:
    """The card is assembled from counts, so it cannot claim anything unsupported."""
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", 5)

    card = await SceneMemory(db).build_card("group:1")

    assert card.memory_count == 5
    assert card.topics, "a scope with memories should name at least one topic"
    assert "5" in card.summary


@pytest.mark.asyncio
async def test_an_empty_scope_yields_an_empty_card_not_an_error(db: Database) -> None:
    """A brand-new group has no card yet; asking must not raise."""
    card = await SceneMemory(db).build_card("group:empty")

    assert card.memory_count == 0
    assert card.topics == []


@pytest.mark.asyncio
async def test_the_card_reads_a_bounded_number_of_rows(db: Database) -> None:
    """The card is injected every turn, so its cost must not scale with history.

    This is the property that makes it safe to inject unconditionally. Without the bound,
    a long-running group would turn every message into a full-table scan.

    The bound applies to the *sample*, not to the reported count. Seeding
    ``CARD_SOURCE_LIMIT + 30`` rows with a topic that only the oldest 30 carry proves
    both halves at once: the count is the true total (so a reader is not told a busy
    group has 200 memories), while the topics come from the bounded window (so the
    out-of-window topic never appears).
    """
    store = MemoryStore(db, embedder=None)
    # An ASCII marker survives tokenisation as one token, so its absence from the card is
    # unambiguous — CJK content is bigrammed and would make the assertion fuzzy.
    await _seed(store, "group:big", 30, text="outofwindow")
    await _seed(store, "group:big", CARD_SOURCE_LIMIT)

    card = await SceneMemory(db).build_card("group:big")

    assert card.memory_count == CARD_SOURCE_LIMIT + 30
    assert "outofwindow" not in card.topics
    assert len(card.topics) <= CARD_TOPIC_LIMIT


@pytest.mark.asyncio
async def test_a_card_round_trips_through_storage(db: Database) -> None:
    """Saving then reading must preserve the fields the prompt depends on."""
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", 4)

    card = await scene.build_card("group:1", title="测试群")
    await scene.save_card(card)
    loaded = await scene.get_card("group:1")

    assert loaded is not None
    assert loaded.title == "测试群"
    assert loaded.topics == card.topics
    assert loaded.memory_count == card.memory_count


@pytest.mark.asyncio
async def test_saving_a_card_twice_replaces_rather_than_duplicates(db: Database) -> None:
    """A card is a view, not a history. Two rows would mean two answers to "current"."""
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", 3)

    await scene.save_card(await scene.build_card("group:1"))
    await _seed(store, "group:1", 2)
    await scene.save_card(await scene.build_card("group:1"))

    loaded = await scene.get_card("group:1")
    assert loaded is not None
    assert loaded.memory_count == 5


# --------------------------------------------------------------- portraits


@pytest.mark.asyncio
async def test_a_thin_scope_gets_no_portrait(db: Database) -> None:
    """Three messages is not a pattern.

    An empty portrait is returned rather than a thin one because a portrait is injected as
    fact. "This group talks about X" derived from three messages is a guess, and a guess
    presented as fact is worse than silence.
    """
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:thin", PORTRAIT_MIN_MEMORIES - 1)

    portrait = await SceneMemory(db).build_portrait("group:thin")

    assert portrait.memory_count == PORTRAIT_MIN_MEMORIES - 1
    assert portrait.headline == ""
    assert portrait.themes == []


@pytest.mark.asyncio
async def test_a_scope_with_enough_evidence_gets_a_portrait(db: Database) -> None:
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:rich", PORTRAIT_MIN_MEMORIES + 5)

    portrait = await SceneMemory(db).build_portrait("group:rich")

    assert portrait.headline
    assert portrait.themes
    assert 0.0 < portrait.confidence <= 1.0


@pytest.mark.asyncio
async def test_confidence_saturates_rather_than_growing_without_bound(db: Database) -> None:
    """A thousand memories is not ten times more certain than a hundred."""
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:many", 200)

    portrait = await SceneMemory(db).build_portrait("group:many")

    assert portrait.confidence <= 1.0


@pytest.mark.asyncio
async def test_a_portrait_round_trips_through_storage(db: Database) -> None:
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", PORTRAIT_MIN_MEMORIES + 2)

    portrait = await scene.build_portrait("group:1")
    await scene.save_portrait(portrait)
    loaded = await scene.get_portrait("group:1")

    assert loaded is not None
    assert loaded.headline == portrait.headline
    assert loaded.confidence == portrait.confidence


# ------------------------------------------------------------------- links


@pytest.mark.asyncio
async def test_a_link_is_recorded_and_readable_from_both_ends(db: Database) -> None:
    """``a -> b`` means "same subject", which is symmetric in practice.

    Returning only outgoing edges would make recall depend on which memory happened to be
    written first — a difference the reader cannot see and would not expect.
    """
    scene = SceneMemory(db)
    await scene.link(1, 2, "same_subject")

    assert await scene.neighbours(1) == [2]
    assert await scene.neighbours(2) == [1]


@pytest.mark.asyncio
async def test_linking_the_same_pair_twice_does_not_duplicate(db: Database) -> None:
    """Repeated extraction of the same fact must not multiply the edge."""
    scene = SceneMemory(db)
    await scene.link(1, 2, "same_topic")
    await scene.link(1, 2, "same_topic")

    assert await scene.neighbours(1) == [2]


@pytest.mark.asyncio
async def test_an_unknown_link_kind_is_rejected(db: Database) -> None:
    """An open vocabulary of edge types is one nobody can query later."""
    scene = SceneMemory(db)
    with pytest.raises(ValueError) as caught:
        await scene.link(1, 2, "vibes")
    assert "vibes" in str(caught.value)


def test_the_link_vocabulary_is_closed() -> None:
    assert {"same_subject", "same_topic", "elaborates", "contradicts"} == LINK_KINDS


@pytest.mark.asyncio
async def test_a_self_link_is_ignored(db: Database) -> None:
    """A self-link would make "related memories" return the memory itself."""
    scene = SceneMemory(db)
    await scene.link(7, 7, "same_topic")

    assert await scene.neighbours(7) == []


@pytest.mark.asyncio
async def test_deleting_a_memory_drops_its_edges(db: Database) -> None:
    """Dangling edges resolve to nothing, which reads as data loss to whoever hits it."""
    scene = SceneMemory(db)
    await scene.link(1, 2, "same_subject")
    await scene.link(1, 3, "same_subject")

    removed = await scene.unlink_all(1)

    assert removed == 2
    assert await scene.neighbours(2) == []


@pytest.mark.asyncio
async def test_neighbours_respects_the_limit(db: Database) -> None:
    scene = SceneMemory(db)
    for target in range(2, 10):
        await scene.link(1, target, "same_topic")

    assert len(await scene.neighbours(1, limit=3)) == 3


@pytest.mark.asyncio
async def test_neighbours_returns_each_id_once_strongest_first(db: Database) -> None:
    """Two edges to the same memory are one neighbour, ranked by its strongest edge.

    The union of outgoing and incoming edges can reach the same id twice (once per
    direction, or once per kind). Returning it twice would waste the caller's limit on a
    duplicate, and returning it unordered would make "most related first" a lie.
    """
    scene = SceneMemory(db)
    await scene.link(1, 2, "same_topic", weight=0.2)
    await scene.link(2, 1, "same_subject", weight=0.9)
    await scene.link(1, 3, "same_topic", weight=0.5)

    assert await scene.neighbours(1) == [2, 3]


@pytest.mark.asyncio
async def test_a_weaker_link_does_not_downgrade_a_stronger_one(db: Database) -> None:
    """Weight is evidence strength; a later weak observation must not erase a strong one.

    Observed through the ranking rather than through a new accessor: 2 keeps the 0.9 it
    was first recorded with, so it still outranks 3's 0.5 after the 0.1 repeat.
    """
    scene = SceneMemory(db)
    await scene.link(1, 2, "same_topic", weight=0.9)
    await scene.link(1, 3, "same_topic", weight=0.5)
    await scene.link(1, 2, "same_topic", weight=0.1)

    assert await scene.neighbours(1) == [2, 3]


@pytest.mark.asyncio
async def test_concurrent_refreshes_of_one_scope_do_not_collide(db: Database) -> None:
    """Two turns for the same group can finish their write-back at the same moment.

    A select-then-insert would have both writers see "no row" and the loser would die on
    the UNIQUE constraint — a crash caused purely by timing, on the busiest groups first.
    """
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", PORTRAIT_MIN_MEMORIES + 2)

    await asyncio.gather(
        scene.refresh("group:1"),
        scene.refresh("group:1"),
        scene.refresh("group:1"),
    )

    assert await scene.get_card("group:1") is not None
    assert await scene.get_portrait("group:1") is not None


# ------------------------------------------------------------------ refresh


@pytest.mark.asyncio
async def test_refresh_writes_both_views_back(db: Database) -> None:
    """The write-back step: after new memories land, the derived views are stored."""
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:1", PORTRAIT_MIN_MEMORIES + 3)

    card, portrait = await scene.refresh("group:1", title="群一")

    assert await scene.get_card("group:1") is not None
    assert await scene.get_portrait("group:1") is not None
    assert card.memory_count == portrait.memory_count


@pytest.mark.asyncio
async def test_refresh_does_not_store_a_thin_portrait(db: Database) -> None:
    """Storing an empty portrait would let a later reader mistake it for evidence."""
    scene = SceneMemory(db)
    store = MemoryStore(db, embedder=None)
    await _seed(store, "group:thin", 3)

    await scene.refresh("group:thin")

    assert await scene.get_card("group:thin") is not None
    assert await scene.get_portrait("group:thin") is None


# ------------------------------------------------------------------- skills


def test_recurring_memories_become_a_skill_candidate() -> None:
    """Three mentions of the same topic is the smallest defensible pattern."""
    forge = SkillForge(root=__import__("pathlib").Path("."))
    memories = [
        (1, "部署需要先装 docker", "部署 docker"),
        (2, "部署脚本在 scripts 目录", "部署 scripts"),
        (3, "部署完记得看健康检查", "部署 健康"),
    ]

    candidates = forge.candidates(memories)

    assert candidates
    assert candidates[0].topic == "部署"
    assert candidates[0].support == 3


def test_two_mentions_are_not_enough() -> None:
    """Two is a coincidence, not a pattern."""
    forge = SkillForge(root=__import__("pathlib").Path("."))
    memories = [
        (1, "部署需要先装 docker", "部署"),
        (2, "部署脚本在 scripts 目录", "部署"),
    ]

    assert forge.candidates(memories) == []
    assert MIN_SUPPORT == 3


def test_a_duplicated_sentence_counts_once() -> None:
    """The same sentence extracted twice is one piece of evidence, not two."""
    forge = SkillForge(root=__import__("pathlib").Path("."))
    memories = [
        (1, "部署需要先装 docker", "部署"),
        (2, "部署需要先装 docker", "部署"),
        (3, "部署需要先装 docker", "部署"),
    ]

    assert forge.candidates(memories) == []


def test_a_skill_is_written_as_markdown_with_front_matter(tmp_path) -> None:
    """A skill is a file the operator can open, edit and delete — that is the point."""
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates(
        [
            (1, "部署需要先装 docker", "部署"),
            (2, "部署脚本在 scripts 目录", "部署"),
            (3, "部署完记得看健康检查", "部署"),
        ]
    )[0]

    skill = forge.build("group:1", candidate)
    path = forge.save(skill)

    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "kind: memory-skill" in text
    assert "部署" in text


def test_a_saved_skill_can_be_loaded_back(tmp_path) -> None:
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates(
        [(i, f"部署第{i}步", "部署") for i in range(3)]
    )[0]
    forge.save(forge.build("group:1", candidate))

    loaded = forge.load("group:1")

    assert len(loaded) == 1
    assert loaded[0].scope == "group:1"
    assert loaded[0].support == 3


def test_skills_are_private_to_their_scope(tmp_path) -> None:
    """A skill distilled from group A's conversation is group A's.

    Copying it to group B would leak both the content and the fact that A discussed it,
    which is why there is no "load all scopes" method to misuse.
    """
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates([(i, f"部署第{i}步", "部署") for i in range(3)])[0]
    forge.save(forge.build("group:A", candidate))

    assert len(forge.load("group:A")) == 1
    assert forge.load("group:B") == []


def test_a_scope_cannot_escape_its_directory(tmp_path) -> None:
    """The scope comes from a session key derived from transport input.

    A scope containing ``..`` would put the file outside the vault, and the only symptom
    would be that the skill "does not load".
    """
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates([(i, f"部署第{i}步", "部署") for i in range(3)])[0]
    skill = forge.build("../../etc", candidate)

    with pytest.raises(ValueError):
        forge.save(skill)


def test_an_unreadable_skill_does_not_break_the_others(tmp_path) -> None:
    """One bad file must not make the whole scene's skills unreadable."""
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates([(i, f"部署第{i}步", "部署") for i in range(3)])[0]
    forge.save(forge.build("group:1", candidate))
    # The scope is percent-encoded into a directory name; ``group:1`` is not a legal
    # Windows path component, which is exactly why the encoding exists.
    scope_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
    (scope_dir / "broken.md").write_text("---\nnot: valid: yaml\n---\n", encoding="utf-8")

    loaded = forge.load("group:1")

    assert len(loaded) >= 1, "a malformed file took out the good ones"


def test_deleting_a_skill_removes_the_file(tmp_path) -> None:
    forge = SkillForge(root=tmp_path)
    candidate = forge.candidates([(i, f"部署第{i}步", "部署") for i in range(3)])[0]
    skill = forge.build("group:1", candidate)
    forge.save(skill)

    assert forge.delete("group:1", skill.skill_id) is True
    assert forge.load("group:1") == []
    assert forge.delete("group:1", skill.skill_id) is False
