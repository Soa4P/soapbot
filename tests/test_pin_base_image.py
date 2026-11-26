"""Pinning the base image: the rewrite is mechanical, so test the mechanics (S-DEP-08).

Two ``FROM`` lines in one Dockerfile (build + runtime), the same image tag. A pin that only
catches the first would leave the runtime stage — the one that actually ships — floating.
The lookup half needs the network, so it is exercised through ``--digest``; what is tested
here is the part that can silently corrupt a Dockerfile.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pin_base_image_digest as pin
import pytest

DIGEST = "sha256:" + "b" * 64

SAMPLE = """\
FROM python:3.12-slim AS build
RUN true
FROM python:3.12-slim AS runtime
RUN true
FROM alpine:3.20 AS other
"""


def test_every_stage_using_the_image_is_pinned() -> None:
    """Both stages, not just the first: the runtime stage is the one that ships."""
    updated, count = pin.rewrite(SAMPLE, "python:3.12-slim", DIGEST)
    assert count == 2
    assert updated.count(f"python:3.12-slim@{DIGEST}") == 2
    # A different image is untouched, alias preserved, and the file keeps its shape.
    assert "FROM alpine:3.20 AS other" in updated
    assert "FROM python:3.12-slim AS build" not in updated


def test_an_already_pinned_line_is_repinned() -> None:
    """Re-pinning is the normal operation; refusing it would push people to hand-editing."""
    once, _ = pin.rewrite(SAMPLE, "python:3.12-slim", DIGEST)
    twice, count = pin.rewrite(once, "python:3.12-slim", "sha256:" + "c" * 64)
    assert count == 2
    assert "sha256:" + "b" * 64 not in twice
    assert twice.count("sha256:" + "c" * 64) == 2


def test_a_stage_without_an_alias_is_kept_valid() -> None:
    updated, count = pin.rewrite("FROM python:3.12-slim\n", "python:3.12-slim", DIGEST)
    assert count == 1
    assert updated.strip() == f"FROM python:3.12-slim@{DIGEST}"


@pytest.mark.parametrize(
    "digest", ["sha256:abc", "md5:" + "a" * 64, "", "sha256:" + "z" * 64]
)
def test_a_bad_digest_is_refused(digest: str) -> None:
    with pytest.raises(ValueError):
        pin.rewrite(SAMPLE, "python:3.12-slim", digest)


@pytest.mark.parametrize(
    "image",
    [
        "https://evil.example/python:3.12-slim",
        "python:3.12-slim&&curl evil",
        "python",
        "Python:3.12",
        "python:3.12-slim --platform=linux/amd64",
    ],
)
def test_an_image_that_could_reach_another_url_is_refused(image: str) -> None:
    """The value reaches a URL, so it is validated before it gets anywhere near one."""
    with pytest.raises(ValueError):
        pin.rewrite(SAMPLE, image, DIGEST)


def test_no_matching_from_is_a_failure_not_a_silent_no_op(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(SAMPLE, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(pin.__file__)),
            "--image",
            "python:3.11-slim",
            "--digest",
            DIGEST,
            "--write",
            "--dockerfile",
            str(dockerfile),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1
    assert "no FROM line" in result.stderr


def test_the_cli_writes_when_asked(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(SAMPLE, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(pin.__file__)),
            "--image",
            "python:3.12-slim",
            "--digest",
            DIGEST,
            "--write",
            "--dockerfile",
            str(dockerfile),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert f"python:3.12-slim@{DIGEST}" in dockerfile.read_text(encoding="utf-8")
