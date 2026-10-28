"""Installing a plugin package: one test per way a package can be hostile.

Each case below corresponds to a defence listed in ``plugins/installer.py``. They are
kept separate rather than parametrised because the *reason* each one is rejected is
the documentation — a single "bad archives are rejected" test would pass even if five
of the six checks were removed.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from soapbot.plugins import installer
from soapbot.plugins.installer import InstallError, install_from_zip
from soapbot.plugins.loader import PluginLoader

MANIFEST = """\
name: demo
version: 1.0.0
description: a test plugin
entry: main:Plugin
trust: community
capabilities:
  - command
"""

MAIN = "class Plugin:\n    def setup(self, ctx):\n        return None\n"


def _zip(entries: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _good() -> bytes:
    return _zip(
        {
            "demo/plugin.yaml": MANIFEST,
            "demo/main.py": MAIN,
        }
    )


def test_installs_a_well_formed_package(tmp_path: Path) -> None:
    result = install_from_zip(_good(), tmp_path)

    assert result.name == "demo"
    assert (tmp_path / "demo" / "plugin.yaml").is_file()
    assert (tmp_path / "demo" / "main.py").is_file()
    assert result.files == 2
    assert result.digest


def test_installing_does_not_approve(tmp_path: Path) -> None:
    """If upload implied approval, uploading a file would be the entire attack."""
    result = install_from_zip(_good(), tmp_path)
    assert result.to_dict()["approved"] is False

    loader = PluginLoader(plugins_dir=tmp_path)
    report = loader.discover()
    assert [m.name for m in report.found] == ["demo"]
    assert loader.is_approved("demo") is False
    assert loader.approved_capabilities("demo") == frozenset()


def test_rejects_path_traversal(tmp_path: Path) -> None:
    payload = _zip({"demo/plugin.yaml": MANIFEST, "../../evil.py": "x"})
    with pytest.raises(InstallError, match="traversal|escapes"):
        install_from_zip(payload, tmp_path)
    assert not (tmp_path.parent / "evil.py").exists()


def test_rejects_absolute_paths(tmp_path: Path) -> None:
    payload = _zip({"demo/plugin.yaml": MANIFEST, "/etc/passwd": "x"})
    with pytest.raises(InstallError, match="absolute"):
        install_from_zip(payload, tmp_path)


def test_rejects_symlink_entries(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("demo/plugin.yaml", MANIFEST)
        info = zipfile.ZipInfo("demo/link")
        info.external_attr = (0o120777 << 16)  # symlink mode bits
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(InstallError, match="symlink"):
        install_from_zip(buf.getvalue(), tmp_path)


def test_rejects_too_many_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "MAX_ENTRIES", 3)
    payload = _zip(
        {"demo/plugin.yaml": MANIFEST, "demo/a.txt": "a", "demo/b.txt": "b", "demo/c.txt": "c"}
    )
    with pytest.raises(InstallError, match="entries"):
        install_from_zip(payload, tmp_path)


def test_rejects_a_decompression_bomb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The header's size can lie, so the cap is enforced on bytes actually written."""
    monkeypatch.setattr(installer, "MAX_UNCOMPRESSED_BYTES", 4096)
    payload = _zip({"demo/plugin.yaml": MANIFEST, "demo/big.txt": "A" * 200_000})
    with pytest.raises(InstallError, match="size limit|expands"):
        install_from_zip(payload, tmp_path)
    assert not (tmp_path / "demo").exists()


def test_rejects_package_with_two_manifests(tmp_path: Path) -> None:
    payload = _zip(
        {
            "demo/plugin.yaml": MANIFEST,
            "other/plugin.yaml": MANIFEST.replace("demo", "other"),
        }
    )
    with pytest.raises(InstallError, match="exactly one"):
        install_from_zip(payload, tmp_path)


def test_rejects_manifest_nested_too_deep(tmp_path: Path) -> None:
    payload = _zip({"a/b/plugin.yaml": MANIFEST, "a/b/main.py": MAIN})
    with pytest.raises(InstallError, match="root or under one directory"):
        install_from_zip(payload, tmp_path)


def test_rejects_entry_outside_the_wrapping_directory(tmp_path: Path) -> None:
    """A stray file at the root makes the layout ambiguous, so it is refused.

    Either error is correct — the point is that the archive is not "helpfully"
    installed with the stray file dropped, because the next reader would have to
    guess which of the two layouts the author meant.
    """
    payload = _zip({"demo/plugin.yaml": MANIFEST, "stray.py": "x"})
    with pytest.raises(InstallError, match="outside the plugin directory|under one directory"):
        install_from_zip(payload, tmp_path)


def test_replaces_an_existing_version_and_leaves_no_staging_dirs(tmp_path: Path) -> None:
    install_from_zip(_good(), tmp_path)
    second = _zip({"demo/plugin.yaml": MANIFEST.replace("1.0.0", "2.0.0"), "demo/main.py": MAIN})
    result = install_from_zip(second, tmp_path)

    assert result.replaced is True
    assert result.version == "2.0.0"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith((".staging", ".retired"))]
    assert leftovers == []


def test_a_rejected_install_leaves_the_existing_version_intact(tmp_path: Path) -> None:
    install_from_zip(_good(), tmp_path)
    before = (tmp_path / "demo" / "plugin.yaml").read_text(encoding="utf-8")

    with pytest.raises(InstallError):
        install_from_zip(_zip({"demo/plugin.yaml": MANIFEST, "../../x": "y"}), tmp_path)

    assert (tmp_path / "demo" / "plugin.yaml").read_text(encoding="utf-8") == before
