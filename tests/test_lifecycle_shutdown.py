"""Shutdown and resource lifetime: bounded waits, temp cleanup, Windows job objects."""

from __future__ import annotations

import os
import time
from pathlib import Path

import soapbot.plugins.job_object as job_object
from soapbot.config import settings


def test_shutdown_has_a_bound() -> None:
    """An unbounded shutdown turns one stuck adapter into a hang on every restart."""
    assert settings.shutdown_grace_seconds >= 1


def test_uvicorn_keeps_our_logging_and_bounds_shutdown() -> None:
    cli = (Path(__file__).resolve().parents[1] / "src" / "soapbot" / "cli.py").read_text(
        encoding="utf-8"
    )

    assert "log_config=None" in cli, "uvicorn would replace the root handlers"
    assert "timeout_graceful_shutdown=settings.shutdown_grace_seconds" in cli


def test_job_object_is_a_noop_off_windows() -> None:
    """The guard must not raise on Linux, where killpg already covers the group."""
    if os.name == "nt":
        # On Windows the call is real; an impossible pid must still fail quietly
        # rather than raise into the caller that is starting a worker.
        assert job_object.assign(999_999_999) is False
    else:
        assert job_object.assign(12345) is False


def test_stale_temp_is_removed_and_fresh_temp_is_kept(tmp_path, monkeypatch) -> None:
    from soapbot.app import _clean_stale_temp

    tmp = tmp_path / "tmp"
    tmp.mkdir()
    stale = tmp / "old-upload.bin"
    fresh = tmp / "current-upload.bin"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"x")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _clean_stale_temp()

    assert not stale.exists(), "a day-old leftover should be gone"
    assert fresh.exists(), "a recent file may still be in use"


def test_missing_temp_directory_is_not_an_error(tmp_path, monkeypatch) -> None:
    from soapbot.app import _clean_stale_temp

    monkeypatch.setattr(settings, "data_dir", tmp_path / "does-not-exist")

    _clean_stale_temp()  # must not raise
