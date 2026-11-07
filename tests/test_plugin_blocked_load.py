"""A block added *after* installation must stop the plugin from running.

`install_from_zip` refuses blocked versions at upload time, and `/api/plugins` shows a
warning for an installed one — but neither of those stops execution. A release is
usually blocked because a vulnerability was found, i.e. after it has already shipped,
so the important case is precisely the package that is sitting on disk, approved,
and about to be auto-loaded on the next restart.

Every test here asserts the code was **not imported**, not merely that an exception was
raised. A check placed after `_import_plugin` has already executed the bytes it was
supposed to vet; that failure mode has bitten this loader more than once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from soapbot.plugins.approvals import ApprovalStore
from soapbot.plugins.integrity import forget
from soapbot.plugins.loader import PluginLoader, PluginLoadError
from soapbot.plugins.manifest import block_key

NAME = "demo"
VERSION = "1.0.0"
REASON = "该版本会泄露凭据"

MANIFEST = """\
name: demo
version: 1.0.0
description: a plugin used by the blocklist tests
entry: main:Plugin
trust: untrusted
capabilities: []
"""

MAIN = """\
class Plugin:
    def setup(self, ctx):
        pass
"""


def _write_plugin(root: Path) -> Path:
    directory = root / NAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.yaml").write_text(MANIFEST, encoding="utf-8")
    (directory / "main.py").write_text(MAIN, encoding="utf-8")
    forget(directory)
    return directory


def _blocklist(path: Path, *, version: str = VERSION, reason: str = REASON) -> Path:
    path.write_text(
        json.dumps({"blocked": [{"name": NAME, "version": version, "reason": reason}]}),
        encoding="utf-8",
    )
    return path


def _loader(
    root: Path,
    tmp_path: Path,
    *,
    blocklist_path: Path | None = None,
    blocked_provider=None,
) -> PluginLoader:
    return PluginLoader(
        plugins_dir=root,
        approvals=ApprovalStore(tmp_path / "approvals.json"),
        blocklist_path=blocklist_path,
        blocked_provider=blocked_provider,
    )


def _assert_never_imported(loader: PluginLoader) -> None:
    assert NAME not in loader._loaded
    assert f"soapbot_plugins.{NAME}" not in sys.modules


@pytest.mark.asyncio
async def test_a_shipped_block_refuses_load_before_import(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    _write_plugin(root)
    blocks = _blocklist(tmp_path / "blocked.json")
    loader = _loader(root, tmp_path, blocklist_path=blocks)
    loader.approve(NAME, set())

    with pytest.raises(PluginLoadError) as info:
        await loader.load(NAME)

    assert "blocked" in str(info.value)
    assert REASON in str(info.value)
    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_the_reason_is_recorded_in_the_audit_trail(tmp_path: Path) -> None:
    from soapbot.security.audit import get_audit_log

    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(root, tmp_path, blocklist_path=_blocklist(tmp_path / "blocked.json"))
    loader.approve(NAME, set())

    with pytest.raises(PluginLoadError):
        await loader.load(NAME)

    denies = [
        event
        for event in get_audit_log().recent(limit=100)
        if event["action"] == "load" and event["outcome"] == "deny" and "blocked" in event["detail"]
    ]
    assert denies, "a refused load must leave an attributable reason"


@pytest.mark.asyncio
async def test_force_cannot_bypass_a_block(tmp_path: Path) -> None:
    """`reload()` passes force=True; that must not become a one-click bypass."""
    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(root, tmp_path, blocklist_path=_blocklist(tmp_path / "blocked.json"))

    with pytest.raises(PluginLoadError, match="blocked"):
        await loader.load(NAME, force=True)

    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_reload_of_a_previously_running_plugin_is_refused(tmp_path: Path) -> None:
    """The real scenario: it was fine yesterday, the index added a block, now reload."""
    state: dict[str, str] = {}

    async def provider() -> dict[str, str]:
        return state

    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(root, tmp_path, blocked_provider=provider)
    loader.approve(NAME, set())
    await loader.load(NAME)
    assert NAME in loader._loaded

    state[block_key(NAME, VERSION)] = REASON

    with pytest.raises(PluginLoadError, match="blocked"):
        await loader.reload(NAME)

    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_a_remote_block_is_enforced_by_the_manager_provider(tmp_path: Path) -> None:
    from soapbot.plugins.dispatch import PluginManager
    from soapbot.plugins.index_client import IndexSnapshot

    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(root, tmp_path, blocklist_path=tmp_path / "absent.json")
    assert loader.blocked_provider is None, "isolated loader starts with no remote source"

    manager = PluginManager(loader)
    assert loader.blocked_provider is not None, "the manager must wire the live blocklist"

    async def remote(*, force: bool = False) -> IndexSnapshot:
        return IndexSnapshot(
            available=True, blocked={block_key(NAME, VERSION): "索引标记不安全"}
        )

    manager.index.snapshot = remote  # type: ignore[method-assign]

    loader.approve(NAME, set())
    with pytest.raises(PluginLoadError, match="索引标记不安全"):
        await loader.load(NAME)

    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_a_broken_index_does_not_lift_a_local_block(tmp_path: Path) -> None:
    async def broken() -> dict[str, str]:
        raise OSError("index unreachable")

    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(
        root,
        tmp_path,
        blocklist_path=_blocklist(tmp_path / "blocked.json"),
        blocked_provider=broken,
    )
    loader.approve(NAME, set())

    with pytest.raises(PluginLoadError, match="blocked"):
        await loader.load(NAME)

    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_a_broken_index_does_not_block_a_clean_plugin(tmp_path: Path) -> None:
    """Fail-open for remote-only data: GitHub being down must not break every plugin."""

    async def broken() -> dict[str, str]:
        raise OSError("index unreachable")

    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(
        root, tmp_path, blocklist_path=tmp_path / "absent.json", blocked_provider=broken
    )
    loader.approve(NAME, set())

    loaded = await loader.load(NAME)
    assert loaded.name == NAME
    await loader.unload(NAME)


@pytest.mark.asyncio
async def test_load_approved_reports_the_block_instead_of_crashing_startup(
    tmp_path: Path,
) -> None:
    """Startup collects per-plugin failures; a block must be one of them."""
    root = tmp_path / "plugins"
    _write_plugin(root)
    loader = _loader(root, tmp_path, blocklist_path=_blocklist(tmp_path / "blocked.json"))
    loader.approve(NAME, set())

    report = await loader.load_approved()

    assert report.loaded == []
    assert len(report.failed) == 1
    assert report.failed[0][0] == NAME
    assert "blocked" in report.failed[0][1]
    _assert_never_imported(loader)


@pytest.mark.asyncio
async def test_a_block_on_another_release_does_not_block_this_one(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    _write_plugin(root)
    blocks = _blocklist(tmp_path / "blocked.json", version="2.0.0")
    loader = _loader(root, tmp_path, blocklist_path=blocks)
    loader.approve(NAME, set())

    loaded = await loader.load(NAME)
    assert loaded.name == NAME
    await loader.unload(NAME)


@pytest.mark.asyncio
async def test_the_short_version_spelling_does_not_bypass_the_block(tmp_path: Path) -> None:
    """`1.0` in a block and `1.0.0` in the manifest are the same release."""
    root = tmp_path / "plugins"
    _write_plugin(root)
    blocks = _blocklist(tmp_path / "blocked.json", version="1.0")
    loader = _loader(root, tmp_path, blocklist_path=blocks)
    loader.approve(NAME, set())

    with pytest.raises(PluginLoadError, match="blocked"):
        await loader.load(NAME)

    _assert_never_imported(loader)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["load_plugin", "reload_plugin"])
async def test_the_api_names_a_block_without_echoing_index_text(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """403 with a fixed reason: the blocklist is third-party data.

    The generic load-error handler strips exception text because plugin-authored
    strings must not reach a browser. But `load failed: PluginLoadError` tells an
    operator nothing about a block, so this one case gets its own response — with a
    constant detail, never the index's `reason`.
    """
    from fastapi import HTTPException

    from soapbot.api import plugins as plugins_api
    from soapbot.plugins.loader import PluginBlockedError

    class FakeManager:
        async def load(self, name):
            raise PluginBlockedError("blocked: <script>alert(1)</script>")

        async def reload(self, name):
            raise PluginBlockedError("blocked: <script>alert(1)</script>")

    monkeypatch.setattr("soapbot.app.get_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(plugins_api, "_authorize", lambda _request: None)

    with pytest.raises(HTTPException) as info:
        await getattr(plugins_api, endpoint)(NAME, object())  # type: ignore[arg-type]

    assert info.value.status_code == 403
    assert "blocked" in info.value.detail
    assert "<script>" not in info.value.detail
