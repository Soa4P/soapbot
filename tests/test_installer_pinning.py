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


# ------------------------------------------------------- archive contents (S-DEP-23)


def test_the_refusal_runs_before_anything_is_unpacked() -> None:
    """Order is the whole defence: a hostile archive must not even reach the temp dir."""
    text = INSTALLER.read_text(encoding="utf-8")
    check = text.index("^[^/]+/(data|\\.venv)(/|$)")
    assert check < text.index("tar -xzf"), "归档检查必须在解包之前"


def test_the_top_level_only_pattern_is_what_is_used() -> None:
    """Only *top-level* data/ and .venv/ are refused.

    Without the leading anchor the pattern would also refuse `src/.../data/` or any
    fixture directory called `data`, turning a safety check into a permanent install
    failure for a legitimate tree.
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert "'^[^/]+/(data|\\.venv)(/|$)'" in text


@linux_only
def test_an_archive_carrying_data_is_refused_before_unpacking(tmp_path: Path) -> None:
    """End to end, with the network and Python faked out.

    This is the failure the check exists for: a tag or mirror whose archive contains
    ``data/``. Unpacked over a live install it replaces the database, ``.env``, the JWT
    key and the secret box — and the old installer copied whatever the archive held,
    having no reason to look.
    """
    import io
    import os
    import tarfile

    archive = tmp_path / "hostile.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        payload = b"SOAPBOT_HOST=127.0.0.1\n"
        entry = tarfile.TarInfo("soapbot-master/data/.env")
        entry.size = len(payload)
        tf.addfile(entry, io.BytesIO(payload))

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "python3.12").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    # Serves the fixture for any download the installer attempts.
    (fakebin / "curl").write_text(
        "#!/bin/sh\n"
        'out=""\n'
        'while [ $# -gt 0 ]; do case "$1" in -o|--output) out="$2"; shift 2 ;; *) shift ;; esac; done\n'
        f'cp "{archive}" "$out"\n',
        encoding="utf-8",
    )
    for name in ("python3.12", "curl"):
        (fakebin / name).chmod(0o755)

    target = tmp_path / "install"
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / "installer.sh"
        shutil.copyfile(INSTALLER, copy)
        result = subprocess.run(
            ["bash", str(copy), "--dir", str(target)],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
        )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "refusing to unpack" in result.stderr
    assert "soapbot-master/data/.env" in result.stderr, "应当指出是哪个条目触发的"
    assert not (target / "data").exists(), "被拒绝的归档不应被解开"


# ----------------------------------------------------- file permissions (S-DEP-19)


def test_the_service_gets_a_private_umask() -> None:
    """The database and keys the *process* creates must not be world-readable.

    `chmod` on the data directory covers what the installer creates; the SQLite file,
    its WAL/SHM siblings, the JWT key and backups are written by the service, so the
    unit needs its own umask.
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert "UMask=0077" in text


def test_the_data_directory_is_created_private() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'chmod 700 "$DATA"' in text
    # The no-systemd branch has no unit to carry the umask, so it sets one itself,
    # before the process that would create the database is started.
    assert text.index("umask 077") < text.index('nohup "$VENV/bin/python"')
