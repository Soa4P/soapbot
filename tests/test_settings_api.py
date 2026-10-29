"""The settings endpoint: a narrow write path, and the boundaries around it.

The endpoint exists to make four behaviour toggles editable from the panel. The tests
below are mostly about what it *refuses*: a generic "write any setting" form would be a
way to reshape the security boundary from a text field, and that is the failure mode
worth pinning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.config import Settings, settings


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Point both the writer and the reader at a temp ``.env``.

    Both sides matter: a test that only checked the written file would pass even if
    ``Settings`` read a different path, which is exactly the bug the panel must not
    have. ``model_config`` is patched so a real reload would read the same file.
    """
    path = tmp_path / ".env"
    # ``model_config`` is a class attribute and cannot be patched on the instance, so
    # the environment variable is the lever — which is also the documented way to
    # relocate the file, meaning the test exercises the supported path rather than a
    # private hack. ``Settings(_env_file=...)`` below covers the read side explicitly.
    monkeypatch.setenv("SOAPBOT_ENV_FILE", str(path))
    return path


@pytest.fixture
def client(env_file, tmp_path, monkeypatch):
    from soapbot.app import create_app

    monkeypatch.setattr(settings, "enable_runtime", False)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    with TestClient(create_app()) as instance:
        yield instance


def test_read_reports_values_and_capabilities(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body["writable"] == [
        "default_locale",
        "voice_enabled",
        "voice_tts_enabled",
        "voice_tts_voice",
    ]
    assert "zh-CN" in body["locales"] and "en-US" in body["locales"]
    # The page greys out the voice-output switch on this field, so the key has to be
    # present and truthful rather than omitted when the extra is missing.
    assert "tts_available" in body["voice"]
    assert body["expected_schema_version"] >= 1


def test_writing_a_writable_setting_persists_to_the_env_file(
    client: TestClient, env_file: Path
) -> None:
    response = client.post("/api/settings", json={"changes": {"voice_enabled": True}})
    assert response.status_code == 200, response.text
    body = response.json()
    # The panel renders this; a silent success would leave the operator believing a
    # restart-time setting is already live.
    assert body["restart_required"] is True
    assert env_file.read_text(encoding="utf-8").strip() == "SOAPBOT_VOICE_ENABLED=true"


def test_the_written_file_is_readable_by_settings(client: TestClient, env_file: Path) -> None:
    """Round trip: what the panel writes, ``Settings`` must parse.

    Guards the "saved but unreadable" failure — a quoted boolean or a stray line break
    would make the next boot fail with no trace back to the panel.
    """
    client.post("/api/settings", json={"changes": {"voice_enabled": True, "default_locale": "en-US"}})
    values = Settings(_env_file=str(env_file))
    assert values.voice_enabled is True
    assert values.default_locale == "en-US"


def test_existing_env_comments_and_foreign_keys_are_preserved(
    client: TestClient, env_file: Path
) -> None:
    """``.env`` belongs to the operator; saving must not rewrite it from scratch.

    A regenerated file would silently drop the comment explaining *why* a value is
    what it is, and any variable this build does not read.
    """
    env_file.write_text(
        "# keep me: bind loopback on purpose\n"
        "SOAPBOT_PORT=6185\n"
        "SOME_OTHER_TOOL_KEY=abc\n",
        encoding="utf-8",
    )
    client.post("/api/settings", json={"changes": {"voice_enabled": True}})

    text = env_file.read_text(encoding="utf-8")
    assert "# keep me: bind loopback on purpose" in text
    assert "SOME_OTHER_TOOL_KEY=abc" in text
    assert "SOAPBOT_PORT=6185" in text
    assert "SOAPBOT_VOICE_ENABLED=true" in text


def test_updating_an_existing_key_replaces_it_in_place_once(
    client: TestClient, env_file: Path
) -> None:
    """Saving twice must not append a second line that silently wins."""
    env_file.write_text("SOAPBOT_VOICE_ENABLED=false\n", encoding="utf-8")
    client.post("/api/settings", json={"changes": {"voice_enabled": True}})
    client.post("/api/settings", json={"changes": {"voice_enabled": False}})

    text = env_file.read_text(encoding="utf-8")
    assert text.count("SOAPBOT_VOICE_ENABLED=") == 1
    assert "SOAPBOT_VOICE_ENABLED=false" in text


@pytest.mark.parametrize(
    "name",
    [
        "host",
        "port",
        "data_dir",
        "master_key",
        "group_allowlist",
        "allow_unknown_private",
        "enable_runtime",
        "jwt_secret",
    ],
)
def test_security_shaping_settings_are_refused(client: TestClient, name: str) -> None:
    """The closed table is the control, not the UI hiding a field.

    Each of these would let a panel user widen the security boundary: rebind the
    service, point storage elsewhere, replace the encryption key, or open the group
    allow-list. A 400 naming the field is the refusal; ignoring unknown keys would let
    the caller believe it worked.
    """
    response = client.post("/api/settings", json={"changes": {name: "x"}})
    assert response.status_code == 400
    assert name in response.json()["detail"]


def test_unknown_locale_is_refused(client: TestClient) -> None:
    response = client.post("/api/settings", json={"changes": {"default_locale": "fr-FR"}})
    assert response.status_code == 400
    assert "fr-FR" in response.json()["detail"]


def test_wrong_type_is_refused_before_touching_the_file(
    client: TestClient, env_file: Path
) -> None:
    """A string ``"true"`` would be written as-is and then fail to parse on boot."""
    response = client.post("/api/settings", json={"changes": {"voice_enabled": "true"}})
    assert response.status_code == 400
    assert not env_file.exists(), "a rejected value must not create or modify the file"


def test_empty_patch_is_refused(client: TestClient) -> None:
    assert client.post("/api/settings", json={"changes": {}}).status_code == 400


def test_a_member_is_refused(client: TestClient) -> None:
    """Writing settings is a config change, not a read: ADMIN and above."""
    from soapbot.api.auth import require_api_auth

    client.app.dependency_overrides[require_api_auth] = lambda: {"role": "member"}
    try:
        response = client.post("/api/settings", json={"changes": {"voice_enabled": True}})
    finally:
        client.app.dependency_overrides.pop(require_api_auth, None)
    assert response.status_code == 403


def test_read_is_allowed_for_a_member(client: TestClient) -> None:
    """The paired case: reading the page must not require ADMIN, or an operator on a
    member token cannot see why voice is off."""
    from soapbot.api.auth import require_api_auth

    client.app.dependency_overrides[require_api_auth] = lambda: {"role": "member"}
    try:
        assert client.get("/api/settings").status_code == 200
    finally:
        client.app.dependency_overrides.pop(require_api_auth, None)


def test_values_are_written_as_the_operator_typed_them(client: TestClient, env_file: Path) -> None:
    """Voice names contain hyphens and title case; they must survive verbatim."""
    client.post("/api/settings", json={"changes": {"voice_tts_voice": "en-US-AriaNeural"}})
    assert "SOAPBOT_VOICE_TTS_VOICE=en-US-AriaNeural" in env_file.read_text(encoding="utf-8")
