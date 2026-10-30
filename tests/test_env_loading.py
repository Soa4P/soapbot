"""The `.env` the process is told to read is the one it must actually read.

In a container the source tree is elsewhere and read-only, so the only writable `.env`
is the one on the data volume, named by `SOAPBOT_ENV_FILE`. Deriving the path from
`__file__` meant the settings page wrote one file and the process read another — which
went unnoticed while every key was a `SOAPBOT_*` setting, because Pydantic opens that
file itself. It becomes visible with the first `api_key: env:NAME`: those resolve from
`os.environ`, and nothing had put them there.
"""

from __future__ import annotations

import os
from pathlib import Path

from soapbot.core.builder import load_dotenv_if_present


def test_reads_the_configured_env_file(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("DEEPSEEK_API_KEY=sk-from-the-volume\n", encoding="utf-8")
    monkeypatch.setenv("SOAPBOT_ENV_FILE", str(env))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    load_dotenv_if_present()

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-the-volume"


def test_a_real_environment_variable_wins(tmp_path: Path, monkeypatch) -> None:
    """The file is a default, not an override.

    An operator who exports a value for one run must not be silently overruled by a file
    a previous session left behind — that is the kind of bug where the shell says one
    thing and the process does another.
    """
    env = tmp_path / ".env"
    env.write_text("SOAPBOT_PORT=9999\n", encoding="utf-8")
    monkeypatch.setenv("SOAPBOT_ENV_FILE", str(env))
    monkeypatch.setenv("SOAPBOT_PORT", "6185")

    load_dotenv_if_present()

    assert os.environ["SOAPBOT_PORT"] == "6185"


def test_a_missing_file_is_not_an_error(tmp_path: Path, monkeypatch) -> None:
    """A first run has no `.env` yet; that is a normal state, not a failure."""
    monkeypatch.setenv("SOAPBOT_ENV_FILE", str(tmp_path / "nope.env"))

    load_dotenv_if_present()  # must not raise
