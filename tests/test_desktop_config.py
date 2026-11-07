"""The desktop gate has to fail on the mistakes it claims to catch.

A static checker that only ever prints "ok" is indistinguishable from one that checks
nothing, and this repository has already shipped that mistake once (a gate whose needle
was absent from every file it scanned). So each rule is exercised twice: once against the
real configuration, and once against a deliberately broken copy.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_desktop  # noqa: E402


@pytest.fixture()
def shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the real shell, so a test can break one file without touching the repo."""
    target = tmp_path / "desktop"
    shutil.copytree(ROOT / "desktop", target)
    monkeypatch.setattr(check_desktop, "DESKTOP", target)
    monkeypatch.setattr(check_desktop, "CONF", target / "src-tauri" / "tauri.conf.json")
    monkeypatch.setattr(check_desktop, "CARGO", target / "src-tauri" / "Cargo.toml")
    monkeypatch.setattr(check_desktop, "MAIN_RS", target / "src-tauri" / "src" / "main.rs")
    monkeypatch.setattr(check_desktop, "UI", target / "ui")
    return target


def _rewrite_conf(shell: Path, mutate) -> None:
    path = shell / "src-tauri" / "tauri.conf.json"
    conf = json.loads(path.read_text(encoding="utf-8"))
    mutate(conf)
    path.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")


def test_repository_shell_passes() -> None:
    """The checked-in configuration must satisfy every rule."""
    assert check_desktop.main([]) == 0


def test_wildcard_connect_src_is_rejected(shell: Path) -> None:
    _rewrite_conf(
        shell,
        lambda conf: conf["app"]["security"].__setitem__(
            "csp", conf["app"]["security"]["csp"].replace(
                "connect-src http://127.0.0.1:6185", "connect-src *"
            )
        ),
    )

    findings = check_desktop.check_csp()

    assert any(not f.ok and f.code == "csp.wildcard" for f in findings)
    assert any(not f.ok and f.code == "csp.connect" for f in findings)


def test_missing_csp_is_rejected(shell: Path) -> None:
    _rewrite_conf(shell, lambda conf: conf["app"]["security"].__setitem__("csp", ""))

    findings = check_desktop.check_csp()

    assert [f.code for f in findings] == ["csp.missing"]


def test_remote_script_is_rejected(shell: Path) -> None:
    page = shell / "ui" / "index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</body>", '<script src="https://cdn.example.com/x.js"></script></body>'
        ),
        encoding="utf-8",
    )

    finding = check_desktop.check_no_remote()

    assert not finding.ok
    assert "cdn.example.com" in finding.evidence


def test_schema_url_is_not_treated_as_a_remote_asset(shell: Path) -> None:
    """`$schema` is an editor hint; flagging it makes a correct config look broken."""
    finding = check_desktop.check_no_remote()

    assert finding.ok, finding.evidence


def test_missing_single_instance_plugin_is_rejected(shell: Path) -> None:
    cargo = shell / "src-tauri" / "Cargo.toml"
    cargo.write_text(
        cargo.read_text(encoding="utf-8").replace("tauri-plugin-single-instance", "# removed"),
        encoding="utf-8",
    )

    findings = check_desktop.check_single_instance()

    assert [f.ok for f in findings] == [False, True]


def test_probe_requires_a_timeout(shell: Path) -> None:
    script = shell / "ui" / "main.js"
    script.write_text(
        script.read_text(encoding="utf-8").replace("AbortController", "Object"),
        encoding="utf-8",
    )

    assert not check_desktop.check_probe().ok


def test_spawning_the_backend_is_rejected(shell: Path) -> None:
    """Two supervisors on one port is the failure this rule exists for."""
    main_rs = shell / "src-tauri" / "src" / "main.rs"
    main_rs.write_text(
        main_rs.read_text(encoding="utf-8")
        + '\nfn _spawn() { let _ = std::process::Command::new("python"); }\n',
        encoding="utf-8",
    )

    finding = check_desktop.check_no_spawn()

    assert not finding.ok
    assert "std::process::Command" in finding.evidence


def test_missing_icon_is_reported_by_name(shell: Path) -> None:
    (shell / "src-tauri" / "icons" / "32x32.png").unlink()

    finding = check_desktop.check_icons()

    assert not finding.ok
    assert "32x32.png" in finding.evidence


def test_tray_requires_both_feature_and_builder(shell: Path) -> None:
    cargo = shell / "src-tauri" / "Cargo.toml"
    cargo.write_text(
        cargo.read_text(encoding="utf-8").replace('features = ["tray-icon"]', "features = []"),
        encoding="utf-8",
    )

    assert not check_desktop.check_tray().ok
