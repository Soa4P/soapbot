"""Persona cards are editable from the panel.

The card is Markdown with YAML front matter, and the reason it stayed read-only was
that a field-by-field form would drop the prose body. The fix is not to render the body
as a field: it is to edit the card as the file it is, and to serialise it back through
one function that round-trips every key the loader reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.ai.persona import Persona, PersonaStore, dump_persona_file, load_persona_file


def test_a_card_round_trips_through_the_serialiser(tmp_path: Path) -> None:
    original = Persona(
        id="grumpy",
        name="暴躁老哥",
        system_prompt="你说话很冲，但讲道理。\n\n第二段也不能丢。",
        style="短句，带点讽刺",
        wake_words=["老哥", "bot"],
        banned_words=["亲"],
        max_reply_chars=120,
        temperature=0.9,
        locale="zh-CN",
        version=3,
    )
    path = tmp_path / "grumpy.md"
    path.write_text(dump_persona_file(original), encoding="utf-8")

    loaded = load_persona_file(path)

    assert loaded.id == "grumpy"
    assert loaded.name == "暴躁老哥"
    assert loaded.system_prompt == original.system_prompt
    assert loaded.style == original.style
    assert loaded.wake_words == original.wake_words
    assert loaded.banned_words == original.banned_words
    assert loaded.max_reply_chars == 120
    assert loaded.temperature == 0.9
    assert loaded.locale == "zh-CN"
    assert loaded.version == 3


def test_front_matter_keys_the_panel_does_not_know_about_survive(tmp_path: Path) -> None:
    """An operator's hand-written key must not vanish because the panel saved the card.

    ``extra`` is what the loader collects for unknown keys; carrying it through is the
    difference between "the panel edits the card" and "the panel owns the card".
    """
    path = tmp_path / "custom.md"
    path.write_text(
        "---\nid: custom\nname: Custom\nvoice_id: zh-CN-Yunxi\n---\n\n正文\n",
        encoding="utf-8",
    )
    loaded = load_persona_file(path)
    assert loaded.extra.get("voice_id") == "zh-CN-Yunxi"

    again = load_persona_file(path)
    again.system_prompt = "改过的正文"
    path.write_text(dump_persona_file(again), encoding="utf-8")

    final = load_persona_file(path)
    assert final.extra.get("voice_id") == "zh-CN-Yunxi"
    assert final.system_prompt == "改过的正文"


def test_save_writes_disk_and_updates_the_live_store(tmp_path: Path) -> None:
    """The pipeline reads the store, not the file, so a save must touch both."""
    store = PersonaStore()
    store.load_directory(tmp_path)

    store.save(Persona(id="live", name="Live", system_prompt="第一版"))

    assert store.get("live") is not None
    assert store.get("live").system_prompt == "第一版"
    assert (tmp_path / "live.md").is_file()

    store.save(Persona(id="live", name="Live", system_prompt="第二版", version=2))
    assert store.get("live").system_prompt == "第二版"
    assert "第二版" in (tmp_path / "live.md").read_text(encoding="utf-8")


def test_a_store_without_a_directory_refuses_to_pretend(tmp_path: Path) -> None:
    """A hand-built store has nowhere to write; that must be an error, not a silent no-op."""
    store = PersonaStore()
    assert store.path_for("x") is None
    with pytest.raises(RuntimeError):
        store.save(Persona(id="x", name="X"))
