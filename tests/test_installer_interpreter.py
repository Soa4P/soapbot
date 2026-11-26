"""``install.ps1`` must not run an elevated interpreter out of a user-writable directory.

The attack the audit described (S-DEP-07) needs no bug in Python: the installer runs
elevated, resolves ``python`` through ``PATH``, and ``%LOCALAPPDATA%\\Programs\\Python`` —
or any directory a standard user can write — is on that path. Whoever drops
``python.exe`` there is executed as Administrator, at the moment the bot is being
installed and its future service account configured.

So the rule is not "warn if unusual" but "only execute from directories an unprivileged
user cannot write": ``Program Files`` (and its x86 sibling) and ``SystemRoot``. Anything
else has to be named with ``-PythonExe``, which is the operator vouching for that path.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.ps1"


def _text() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_the_installer_has_a_trusted_root_rule() -> None:
    text = _text()
    assert "Test-TrustedInterpreter" in text, "没有「解释器所在目录是否可信」的判定"
    assert "$TrustedRoots" in text
    assert "$env:ProgramFiles" in text and "$env:SystemRoot" in text
    # The override exists precisely for installs outside those roots.
    assert "[string]$PythonExe" in text


def test_the_resolver_checks_before_it_executes() -> None:
    """Order matters: a check after ``& $exe`` has already executed the attacker's binary."""
    text = _text()
    resolver = text[text.index("function Resolve-Python") :]
    resolver = resolver[: resolver.index("\nWrite-Step \"checking Python 3.12+\"")]
    rejected_at = resolver.index("Test-TrustedInterpreter $resolved")
    invoke_at = resolver.index("Get-PythonVersion $resolved")
    assert rejected_at < invoke_at, "先执行再检查等于没检查"


def test_user_writable_candidates_are_skipped_not_used() -> None:
    text = _text()
    assert "$rejected" in text, "被跳过的解释器要能说出来，否则用户只看到「没找到」"
    assert "user-writable" in text or "用户可写" in text


@pytest.mark.skipif(shutil.which("powershell") is None, reason="PowerShell not available")
def test_the_helper_refuses_a_user_profile_path(tmp_path: Path) -> None:
    """Behaviour, not just text: the same rule evaluated by PowerShell itself."""
    script = tmp_path / "probe.ps1"
    source = _text()
    start = source.index("$TrustedRoots = @(")
    end = source.index("function Get-PythonVersion")
    script.write_text(source[start:end], encoding="utf-8")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ". "
            f"'{script}'; "
            "Write-Output (Test-TrustedInterpreter (Join-Path $env:LOCALAPPDATA 'p\\python.exe'));"
            "Write-Output (Test-TrustedInterpreter (Join-Path $env:ProgramFiles 'p\\python.exe'));"
            "Write-Output (Test-TrustedInterpreter '')",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines == ["False", "True", "False"], result.stdout
