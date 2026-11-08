"""The console-encoding gate must fail on the bug it was written for.

This has already cost two red builds (`verify_restart.py --help`, then
`check_version_consistency.py`), both invisible on a UTF-8 machine and on ubuntu. A gate
that only ever passes is worthless, so the rejection path is tested against a temporary
directory rather than assumed.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_console_encoding.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_console_encoding", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=ROOT,
    )


def test_cjk_detection_covers_the_range() -> None:
    module = _module()

    assert module.has_cjk("版本一致")
    assert module.has_cjk("é 混合 ok")
    assert not module.has_cjk("ascii only")


def test_docstrings_are_not_counted_as_output() -> None:
    """A Chinese docstring never reaches stdout, so it must not trip the gate."""
    module = _module()
    tree = ast.parse('"""中文模块说明"""\n\n\ndef f():\n    """中文函数说明"""\n    return 1\n')

    assert module.printing_strings(tree) == []


def test_a_cjk_print_without_reconfigure_is_rejected(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text('def main() -> int:\n    print("版本一致")\n    return 0\n', encoding="utf-8")

    result = _invoke("--dir", str(tmp_path))

    assert result.returncode == 1, result.stdout
    assert "probe.py" in result.stdout
    assert "reconfigure" in result.stdout


def test_the_same_script_passes_once_it_reconfigures(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\n\n"
        "def main() -> int:\n"
        '    sys.stdout.reconfigure(encoding="utf-8", errors="replace")\n'
        '    print("版本一致")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    result = _invoke("--dir", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_the_repository_passes() -> None:
    result = _invoke()

    assert result.returncode == 0, result.stdout
