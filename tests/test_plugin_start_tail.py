"""A failed isolated start must say *where*, not just *that*.

The child protocol reports only the exception type on the wire ("ValueError") —
plugin-authored text never crosses it. The stack goes to the child's stderr, which the
parent drains into a redacted tail. But a failed start used to discard the worker
object, and with it the tail: the audit row said "isolated start failed: ValueError",
which names a file nobody can find. The supervisor now keeps the tail of the last
failed start, and the loader embeds it in the audit detail.

Found in production: bili-card's first load failed with a bare "ValueError" and no way
to see that the real error was in a specific line of the plugin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.plugins.dispatch import PluginManager
from soapbot.plugins.loader import PluginLoader, PluginLoadError
from soapbot.plugins.supervisor import PluginSupervisor
from soapbot.security.audit import AuditLog
from soapbot.security.crypto import SecretBox

ROOT = Path(__file__).resolve().parents[1]


def _loader(tmp_path: Path, source: str) -> PluginLoader:
    plugins = tmp_path / "plugins" / "tailprobe"
    plugins.mkdir(parents=True)
    (plugins / "main.py").write_text(source, encoding="utf-8")
    (plugins / "plugin.yaml").write_text(
        "name: tailprobe\n"
        "version: 0.1.0\n"
        "entry: main:Probe\n"
        "description: probe plugin for stderr tail propagation\n"
        "author: test\n"
        "trust: community\n"
        "channel: community\n"
        "min_host_version: 0.1.0\n"
        "capabilities: []\n",
        encoding="utf-8",
    )
    loader = PluginLoader(
        plugins_dir=tmp_path / "plugins", audit=AuditLog(),
        supervisor=PluginSupervisor(),
        crypto=SecretBox(key="A" * 43 + "="),
        storage_backend={},
    )
    PluginManager(loader).install_isolation(supervisor=loader.supervisor)
    manifest = next(m for m in loader.discover().found if m.name == "tailprobe")
    loader.approve_from_manifest(manifest)
    return loader


@pytest.mark.asyncio
async def test_the_audit_row_carries_the_child_stderr_tail(tmp_path: Path) -> None:
    loader = _loader(
        tmp_path,
        "class Probe:\n"
        "    async def setup(self, ctx):\n"
        "        raise ValueError('probe-marker-9f3a')\n",
    )
    try:
        with pytest.raises(PluginLoadError):
            await loader.load("tailprobe", force=True)
    finally:
        await loader.supervisor.stop_all()
    events = [e for e in loader.audit.recent(limit=50) if e["action"] == "load"]
    detail = events[-1]["detail"]
    # The wire carries the type…
    assert "isolated start failed: ValueError" in detail
    # …and the tail carries the location, which is the whole point.
    assert "probe-marker-9f3a" in detail or "main.py" in detail


@pytest.mark.asyncio
async def test_a_clean_start_still_loads(tmp_path: Path) -> None:
    loader = _loader(
        tmp_path,
        "from soapbot.plugins.base import Plugin\n\n"
        "class Probe(Plugin):\n"
        "    pass\n",
    )
    try:
        loaded = await loader.load("tailprobe", force=True)
        assert loaded is not None
    finally:
        await loader.supervisor.stop_all()
