"""What the Linux installer installs, and from which exact bytes (audit S-DEP-08).

The one-command installer used to fetch ``master`` and nothing else: whatever the branch
pointed at, with no way to say "these bytes" and no record of what was installed. Two
additions, both cheap and both checkable without a network:

* ``--ref`` accepts a 40-character commit SHA (one tree), a ``vX.Y.Z`` tag, or a branch
  name — and a branch prints a warning, because that ref changes tomorrow;
* ``--sha256`` verifies the downloaded archive and **fails closed**; without it the
  installer prints the digest it got, which is what an operator records for the pin.

The script is exercised by copying it out of the tree and running bash against the copy:
the repository copy is not something to execute inside a test run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"

#: Running the Linux installer under a Windows runner's bash produced UTF-16 output and a
#: non-zero exit for a file that parses fine (`bash -n` on a copy, no output expected). It
#: is not a defect in the script: the target is Linux, and Linux CI runs these. Skipping
#: with the reason stated beats a test that fails for its environment on every push.
linux_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the Linux installer is exercised by the Linux job; Git Bash here is not the target",
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a copy of the installer, so the test never executes the workspace file."""
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / "installer.sh"
        shutil.copyfile(INSTALLER, copy)
        return subprocess.run(
            ["bash", str(copy), *args], capture_output=True, text=True, timeout=120
        )


@linux_only
def test_the_script_parses() -> None:
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / "installer.sh"
        shutil.copyfile(INSTALLER, copy)
        result = subprocess.run(
            ["bash", "-n", str(copy)], capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, result.stderr


def test_the_help_lists_the_pinning_flags() -> None:
    """The flags exist or nobody can use them; the help text is the contract."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "--ref" in text and "--sha256" in text
    assert "-h|--help)" in text


@linux_only
def test_a_short_sha_is_refused_before_anything_is_downloaded() -> None:
    """A typo in a pin must not silently install a branch of the same prefix."""
    result = _run("--ref", "abc123")
    assert result.returncode == 2
    assert "40" in result.stderr


def test_an_option_like_ref_is_refused() -> None:
    """`--ref -o/tmp/x` would be read by curl as a flag; the check is before that."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "must not start with '-'" in text


@linux_only
def test_an_option_like_ref_exits_two_before_downloading() -> None:
    result = _run("--ref", "--output=/tmp/x")
    assert result.returncode == 2
    assert "-" in result.stderr


def test_a_branch_ref_is_accepted_but_warned_about() -> None:
    """A branch is a legitimate choice for "latest"; pretending it is a pin is not."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "that ref changes over time" in text
    assert "reproducible install" in text


def test_the_digest_check_fails_closed() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert "does not match --sha256" in text
    assert "exit 1" in text
    # Both tools are tried: `shasum` is what macOS has, minimal images may have neither.
    assert "sha256sum" in text and "shasum" in text
    assert "no sha256sum/shasum available" in text
