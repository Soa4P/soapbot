"""The one-time login token must not be silently rotated by a restart.

Production evidence: six service starts produced six "generated a one-time bootstrap
token" log lines, and ``init_token.txt`` was overwritten each time. An operator who
wrote the token down found it dead after every deploy, while ``/api/auth/status`` kept
reporting ``login_available: true``.

The fix makes the disk file the authority: reuse an unredeemed credential, destroy it
on redemption, leave a marker so a restart cannot mint a replacement, and require an
explicit ``soapbot token --reset`` to open login again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.security.tokens import (
    BOOTSTRAP_FILE,
    BOOTSTRAP_REDEEMED,
    BootstrapToken,
    bootstrap_for_data_dir,
    reset_bootstrap,
)


def test_a_fresh_install_generates_and_persists(tmp_path: Path) -> None:
    first = bootstrap_for_data_dir(tmp_path)

    assert first.generated is True
    assert first.available is True
    assert (tmp_path / BOOTSTRAP_FILE).read_text(encoding="utf-8").strip() == first.reveal()


def test_an_unused_token_survives_a_restart(tmp_path: Path) -> None:
    """The regression: each start used to mint a different value."""
    first = bootstrap_for_data_dir(tmp_path)
    second = bootstrap_for_data_dir(tmp_path)

    assert second.reveal() == first.reveal()
    assert second.generated is False, "a restart is not a fresh install"
    assert second.available is True
    assert (tmp_path / BOOTSTRAP_FILE).read_text(encoding="utf-8").strip() == first.reveal()


def test_six_restarts_still_give_the_same_token(tmp_path: Path) -> None:
    """The exact shape of the incident, at the same count."""
    values = [bootstrap_for_data_dir(tmp_path).reveal() for _ in range(6)]
    assert len(set(values)) == 1


def test_redeeming_deletes_the_file_and_leaves_a_marker(tmp_path: Path) -> None:
    token = bootstrap_for_data_dir(tmp_path)
    path = tmp_path / BOOTSTRAP_FILE
    marker = tmp_path / BOOTSTRAP_REDEEMED

    assert token.redeem(token.reveal()) is True
    assert not path.exists(), "a spent credential must not stay on disk"
    assert marker.exists(), "without the marker a restart would treat this as a fresh install"
    assert token.consumed is True
    assert token.available is False
    assert token.state == "redeemed"


def test_a_restart_after_redemption_does_not_mint_a_new_token(tmp_path: Path) -> None:
    token = bootstrap_for_data_dir(tmp_path)
    assert token.redeem(token.reveal()) is True

    restarted = bootstrap_for_data_dir(tmp_path)

    assert restarted.available is False
    assert restarted.state == "redeemed"
    assert not (tmp_path / BOOTSTRAP_FILE).exists()
    assert restarted.redeem("anything") is False


def test_wrong_value_does_not_burn_the_token_or_delete_the_file(tmp_path: Path) -> None:
    token = bootstrap_for_data_dir(tmp_path)

    assert token.redeem("not-the-token") is False
    assert (tmp_path / BOOTSTRAP_FILE).exists()
    assert token.available is True
    assert token.redeem(token.reveal()) is True


def test_token_cannot_be_used_twice_across_restarts(tmp_path: Path) -> None:
    """A single-use credential stays single-use even with a process boundary."""
    first = bootstrap_for_data_dir(tmp_path)
    value = first.reveal()
    assert first.redeem(value) is True

    restarted = bootstrap_for_data_dir(tmp_path)
    assert restarted.redeem(value) is False


def test_reset_is_the_only_way_back_in(tmp_path: Path) -> None:
    first = bootstrap_for_data_dir(tmp_path)
    old = first.reveal()
    first.redeem(old)
    assert bootstrap_for_data_dir(tmp_path).available is False

    new = reset_bootstrap(tmp_path)
    assert new != old
    assert not (tmp_path / BOOTSTRAP_REDEEMED).exists()

    after_reset = bootstrap_for_data_dir(tmp_path)
    assert after_reset.available is True
    assert after_reset.reveal() == new
    assert after_reset.redeem(old) is False
    assert after_reset.redeem(new) is True


def test_configured_token_bypasses_the_files(tmp_path: Path) -> None:
    token = bootstrap_for_data_dir(tmp_path, configured="operator-chosen-value")

    assert token.reveal() == "operator-chosen-value"
    assert token.generated is False
    assert not (tmp_path / BOOTSTRAP_FILE).exists()


def test_an_empty_file_is_replaced_not_treated_as_a_credential(tmp_path: Path) -> None:
    (tmp_path / BOOTSTRAP_FILE).write_text("   \n", encoding="utf-8")

    token = bootstrap_for_data_dir(tmp_path)

    assert token.reveal()
    assert (tmp_path / BOOTSTRAP_FILE).read_text(encoding="utf-8").strip() == token.reveal()


def test_a_literal_token_keeps_the_old_in_memory_behaviour() -> None:
    """Tests and embedders construct BootstrapToken("b") directly; no file side effects."""
    token = BootstrapToken("b")
    assert token.generated is False
    assert token.available is True
    assert token.redeem("b") is True
    assert token.redeem("b") is False


def test_marker_write_failure_keeps_the_token_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If redemption cannot be recorded, do not delete the credential.

    Deleting it without the marker would make the next start look like a fresh install
    and mint a new token on its own — silently undoing the single-use guarantee.
    """
    import soapbot.security.tokens as tokens_mod

    token = bootstrap_for_data_dir(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(tokens_mod, "write_private_file", boom, raising=True)

    assert token.redeem(token.reveal()) is True
    assert (tmp_path / BOOTSTRAP_FILE).exists()


# ------------------------------------------------------------------ HTTP surface


@pytest.fixture
def persistent_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A real app lifespan with an on-disk bootstrap token, not a configured literal."""
    from soapbot.api.auth import reset_auth
    from soapbot.app import create_app
    from soapbot.config import settings

    reset_auth()
    monkeypatch.setattr(settings, "data_dir", tmp_path, raising=False)
    monkeypatch.setattr(settings, "init_token", "", raising=False)
    yield create_app, tmp_path
    reset_auth()


def test_http_login_deletes_the_file_and_status_reports_the_state(
    persistent_app,
) -> None:
    from fastapi.testclient import TestClient

    create_app, data_dir = persistent_app
    path = data_dir / BOOTSTRAP_FILE
    marker = data_dir / BOOTSTRAP_REDEEMED

    with TestClient(create_app()) as client:
        assert path.exists(), "the lifespan should persist a fresh credential"
        token = path.read_text(encoding="utf-8").strip()

        before = client.get("/api/auth/status").json()
        assert before["login_available"] is True
        assert before["bootstrap_state"] == "available"

        assert client.post("/api/auth/login", json={"init_token": token}).status_code == 200
        assert not path.exists(), "a spent credential must not stay on disk"
        assert marker.exists()

        after = client.get("/api/auth/status").json()
        assert after["login_available"] is False
        assert after["bootstrap_state"] == "redeemed"


def test_restarting_the_app_does_not_reopen_bootstrap_login(persistent_app) -> None:
    """The regression end to end: a restart used to mint a brand-new credential."""
    from fastapi.testclient import TestClient

    from soapbot.api.auth import reset_auth

    create_app, data_dir = persistent_app
    path = data_dir / BOOTSTRAP_FILE

    with TestClient(create_app()) as client:
        token = path.read_text(encoding="utf-8").strip()
        assert client.post("/api/auth/login", json={"init_token": token}).status_code == 200

    reset_auth()
    with TestClient(create_app()) as restarted:
        assert not path.exists(), "no new token file may be generated after redemption"
        status = restarted.get("/api/auth/status").json()
        assert status["bootstrap_state"] == "redeemed"
        assert status["login_available"] is False
        assert (
            restarted.post("/api/auth/login", json={"init_token": token}).status_code == 401
        )
