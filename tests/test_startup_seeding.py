"""The config directory must exist even when the bot itself is switched off.

Found on a real Windows host: `.env` had `SOAPBOT_ENABLE_RUNTIME=false`, seeding lived
inside `_start_runtime`, so `data/config` was never created — the panel then reported the
config directory as not writable and the first save had nowhere to go. The bot being off is
a supported mode (HTTP-only deployments), and the panel still edits those files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from soapbot.app import create_app
from soapbot.config import settings


def test_config_files_are_seeded_with_runtime_off(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "enable_runtime", False)

    with TestClient(create_app()) as client:
        assert (config_dir / "providers.yaml").is_file()
        assert (config_dir / "adapters.yaml").is_file()

        body = client.get("/api/settings").json()
        assert body["config_dir"] == str(config_dir)
        assert body["config_dir_writable"] is True
