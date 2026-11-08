"""The version is declared in six files; this gate is the only thing comparing them.

Each test pins a different failure mode: the six declarations drifting apart, a runtime
module restating the number instead of importing it, and the command itself stopping
being usable as a gate (non-zero exit, or an exception on a missing file).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_version_consistency.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_version_consistency", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_declaration_agrees() -> None:
    found = _module().sources()

    assert found["src/soapbot/__init__.py"] != "<missing>", "没有解析到 __version__"
    assert len(set(found.values())) == 1, found


def test_every_declaration_is_actually_read() -> None:
    """A source list that silently skips a file would pass while that file drifts."""
    found = _module().sources()

    assert set(found) == {
        "pyproject.toml",
        "src/soapbot/__init__.py",
        "webui/package.json",
        "desktop/package.json",
        "desktop/src-tauri/tauri.conf.json",
        "desktop/src-tauri/Cargo.toml",
    }


def test_runtime_code_does_not_restate_the_version() -> None:
    module = _module()
    version = module.sources()["pyproject.toml"]

    assert module.hardcoded(version) == [], (
        "运行时代码应 import __version__，不要写版本字面量"
    )


def test_cli_exits_zero_on_a_consistent_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
