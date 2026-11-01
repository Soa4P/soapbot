"""A plugin's approval must cover its code, not just its manifest.

The gap these tests close was documented in ``approvals.py`` itself: *"Changing a
plugin's code does not revoke its approval. That is a real gap."* ``digest`` covered
``plugin.yaml``, so replacing ``main.py`` left the manifest byte-identical and the plugin
kept loading as approved — approval was a decision about a directory name.

Every enforcement test here fails if the check is moved after the import, which is the
failure mode this project has hit repeatedly: a control that exists but is not on the
executing path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.plugins.approvals import ApprovalStore
from soapbot.plugins.integrity import compare, digest_tree, forget
from soapbot.plugins.loader import PluginLoader, PluginLoadError

PLUGIN_NAME = "demo"

MANIFEST = """\
name: demo
version: 1.0.0
description: a plugin used by the integrity tests
entry: main:Plugin
trust: untrusted
capabilities: []
"""

MAIN = """\
class Plugin:
    def setup(self, ctx):
        pass
"""


def _write_plugin(root: Path, body: str = MAIN) -> Path:
    directory = root / PLUGIN_NAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.yaml").write_text(MANIFEST, encoding="utf-8")
    (directory / "main.py").write_text(body, encoding="utf-8")
    forget(directory)
    return directory


def _loader(root: Path, tmp_path: Path) -> PluginLoader:
    store = ApprovalStore(tmp_path / "approvals.json")
    return PluginLoader(plugins_dir=root, approvals=store)


# --------------------------------------------------------------------- digesting
def test_digest_covers_code_not_only_the_manifest(tmp_path: Path) -> None:
    """The whole point: editing main.py changes the digest."""
    directory = _write_plugin(tmp_path)
    before = digest_tree(directory)

    (directory / "main.py").write_text(MAIN + "\n# a change\n", encoding="utf-8")
    forget(directory)

    assert digest_tree(directory) != before
    assert before.startswith("sha256:")


def test_a_renamed_file_changes_the_digest(tmp_path: Path) -> None:
    """Content-only hashing would let two files be swapped without detection."""
    directory = _write_plugin(tmp_path)
    (directory / "extra.py").write_text("x = 1\n", encoding="utf-8")
    forget(directory)
    before = digest_tree(directory)

    (directory / "extra.py").rename(directory / "renamed.py")
    forget(directory)

    assert digest_tree(directory) != before


def test_bytecode_is_ignored(tmp_path: Path) -> None:
    """Importing a plugin writes __pycache__; hashing it would flag every load.

    This matters more than it looks: a check that fires on every successful start is a
    check an operator turns off.
    """
    directory = _write_plugin(tmp_path)
    before = digest_tree(directory)

    cache = directory / "__pycache__"
    cache.mkdir()
    (cache / "main.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
    forget(directory)

    assert digest_tree(directory) == before


# ---------------------------------------------------------------- verdict states
def test_unknown_when_nothing_was_recorded(tmp_path: Path) -> None:
    directory = _write_plugin(tmp_path)
    verdict = compare(directory, "")
    assert verdict.state == "unknown"
    assert not verdict.blocks


def test_changed_when_the_tree_differs(tmp_path: Path) -> None:
    directory = _write_plugin(tmp_path)
    recorded = digest_tree(directory)

    (directory / "main.py").write_text("class Plugin: pass\n", encoding="utf-8")
    forget(directory)

    verdict = compare(directory, recorded)
    assert verdict.state == "changed"
    assert verdict.blocks
    assert verdict.recorded == recorded
    assert verdict.current != recorded


# ------------------------------------------------------------------- enforcement
@pytest.mark.asyncio
async def test_changed_code_is_refused_by_default(tmp_path: Path) -> None:
    """block mode: the plugin must not be imported, let alone run."""
    root = tmp_path / "plugins"
    directory = _write_plugin(root)

    loader = _loader(root, tmp_path)
    loader.approve(PLUGIN_NAME, set())
    await loader.load(PLUGIN_NAME)
    await loader.unload(PLUGIN_NAME)

    # The attack: replace the reviewed code, leave the manifest untouched. The body is
    # syntactically valid on purpose — a refusal caused by a syntax error would prove
    # nothing about the digest.
    (directory / "main.py").write_text(
        "class Plugin:\n    def setup(self, ctx):\n        self.executed = True\n",
        encoding="utf-8",
    )
    forget(directory)

    with pytest.raises(PluginLoadError) as excinfo:
        await loader.load(PLUGIN_NAME)

    assert "changed since it was approved" in str(excinfo.value)
    # Not merely "raised": the code must never have been imported.
    assert PLUGIN_NAME not in loader._loaded
    assert f"soapbot_plugins.{PLUGIN_NAME}" not in __import__("sys").modules


@pytest.mark.asyncio
async def test_warn_mode_loads_but_records_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """warn is a deliberate downgrade, and the state must remain visible."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "plugin_integrity_mode", "warn")

    root = tmp_path / "plugins"
    directory = _write_plugin(root)

    loader = _loader(root, tmp_path)
    loader.approve(PLUGIN_NAME, set())
    await loader.load(PLUGIN_NAME)
    await loader.unload(PLUGIN_NAME)

    (directory / "main.py").write_text(MAIN + "\n# hotfix\n", encoding="utf-8")
    forget(directory)

    loaded = await loader.load(PLUGIN_NAME)
    assert loaded.integrity == "changed"
    await loader.unload(PLUGIN_NAME)


@pytest.mark.asyncio
async def test_off_mode_skips_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from soapbot.config import settings

    monkeypatch.setattr(settings, "plugin_integrity_mode", "off")

    root = tmp_path / "plugins"
    directory = _write_plugin(root)

    loader = _loader(root, tmp_path)
    loader.approve(PLUGIN_NAME, set())
    await loader.load(PLUGIN_NAME)
    await loader.unload(PLUGIN_NAME)

    (directory / "main.py").write_text(MAIN + "\n# changed\n", encoding="utf-8")
    forget(directory)

    loaded = await loader.load(PLUGIN_NAME)
    assert loaded.integrity == "unknown"
    await loader.unload(PLUGIN_NAME)


@pytest.mark.asyncio
async def test_an_approval_without_a_recorded_digest_is_not_treated_as_tampering(
    tmp_path: Path,
) -> None:
    """Approvals written before this check existed must not refuse every plugin.

    "We never recorded this" is a different claim from "this changed"; conflating them
    would block every plugin on upgrade, and the operator's fix would be turning the
    check off for good.
    """
    root = tmp_path / "plugins"
    _write_plugin(root)

    store = ApprovalStore(tmp_path / "approvals.json")
    loader = PluginLoader(plugins_dir=root, approvals=store)
    # Simulate a pre-upgrade record: capabilities approved, no content digest.
    store.approve(PLUGIN_NAME, set(), digest="sha256:" + "0" * 64, actor="legacy")
    loader._sync_approvals()

    loaded = await loader.load(PLUGIN_NAME)
    assert loaded.integrity == "unknown"
    await loader.unload(PLUGIN_NAME)


@pytest.mark.asyncio
async def test_re_approving_after_a_change_accepts_the_new_code(tmp_path: Path) -> None:
    """The escape hatch must work, or the control gets disabled instead of used."""
    root = tmp_path / "plugins"
    directory = _write_plugin(root)

    loader = _loader(root, tmp_path)
    loader.approve(PLUGIN_NAME, set())

    (directory / "main.py").write_text(MAIN + "\n# reviewed hotfix\n", encoding="utf-8")
    forget(directory)

    with pytest.raises(PluginLoadError):
        await loader.load(PLUGIN_NAME)

    loader.approve(PLUGIN_NAME, set(), actor="operator")  # the operator re-reviews
    loaded = await loader.load(PLUGIN_NAME)
    assert loaded.integrity == "ok"
    await loader.unload(PLUGIN_NAME)


def test_the_digest_is_persisted_so_a_restart_still_detects_drift(tmp_path: Path) -> None:
    """An approval that forgets what it approved is not an approval."""
    root = tmp_path / "plugins"
    directory = _write_plugin(root)
    store_path = tmp_path / "approvals.json"

    PluginLoader(plugins_dir=root, approvals=ApprovalStore(store_path)).approve(
        PLUGIN_NAME, set()
    )

    (directory / "main.py").write_text("class Plugin: pass\n", encoding="utf-8")
    forget(directory)

    # A fresh loader, as after a restart: it reads the file, not memory.
    fresh = PluginLoader(plugins_dir=root, approvals=ApprovalStore(store_path))
    verdict = fresh.approvals.get(PLUGIN_NAME)
    assert verdict is not None
    assert verdict.content_digest, "content digest was not persisted"
    assert compare(directory, verdict.content_digest).state == "changed"
