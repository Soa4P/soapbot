"""``soapbot setup``: the browser flow, for a machine with no browser.

Three properties are load-bearing, and each has a test that would fail if it regressed:

* a candidate that does not parse is **never** written (otherwise the command that exists
  to make deployment easier becomes a way to brick the next boot);
* the API key never appears on stdout/stderr — the output of this command is what people
  paste into an issue;
* running it twice to fix a model name keeps the key that is already on disk.

The wizard is driven through ``soapbot.cli.main`` rather than by calling ``run`` directly,
so the flags are exercised as documented. Nothing here touches the real ``config/``: the
``config_dir`` is a temporary directory, the same lever the panel uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import soapbot.cli_setup as cli_setup
from soapbot import cli
from soapbot.config import settings


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "config"
    monkeypatch.setattr(settings, "config_dir", target)
    return target


def _run(argv: list[str]) -> int:
    return cli.main(["setup", "--non-interactive", *argv])


def test_non_interactive_flow_writes_a_provider(config_dir: Path) -> None:
    code = _run(
        [
            "--provider-id",
            "deepseek",
            "--base-url",
            "https://api.deepseek.com/v1",
            "--model",
            "deepseek-flash",
            "--skip-adapter",
        ]
    )

    assert code == cli_setup.EXIT_OK
    text = (config_dir / "providers.yaml").read_text(encoding="utf-8")
    assert "deepseek" in text
    assert "https://api.deepseek.com/v1" in text
    assert "deepseek-flash" in text


def test_an_env_reference_is_stored_verbatim_and_the_secret_never_printed(
    config_dir: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("MY_DEEPSEEK_KEY", "sk-super-secret-value")

    code = _run(
        [
            "--provider-id",
            "deepseek",
            "--base-url",
            "https://api.deepseek.com/v1",
            "--model",
            "deepseek-flash",
            "--api-key-env",
            "MY_DEEPSEEK_KEY",
            "--skip-adapter",
        ]
    )

    assert code == cli_setup.EXIT_OK
    text = (config_dir / "providers.yaml").read_text(encoding="utf-8")
    # The reference goes in the file; the value does not.
    assert "env:MY_DEEPSEEK_KEY" in text
    assert "sk-super-secret-value" not in text

    captured = capsys.readouterr()
    assert "sk-super-secret-value" not in captured.out
    assert "sk-super-secret-value" not in captured.err


def test_a_literal_key_is_never_echoed(config_dir: Path, capsys) -> None:
    code = _run(
        [
            "--provider-id",
            "p1",
            "--base-url",
            "https://api.example.com/v1",
            "--model",
            "m1",
            "--api-key",
            "sk-literal-abc123",
            "--skip-adapter",
        ]
    )

    assert code == cli_setup.EXIT_OK
    captured = capsys.readouterr()
    assert "sk-literal-abc123" not in captured.out
    assert "sk-literal-abc123" not in captured.err


def test_an_unresolvable_env_reference_writes_nothing(config_dir: Path, capsys) -> None:
    """The whole point of validating first: a typo must not become a boot-time crash."""
    code = _run(
        [
            "--provider-id",
            "p1",
            "--base-url",
            "https://api.example.com/v1",
            "--model",
            "m1",
            "--api-key-env",
            "DEFINITELY_NOT_SET_ANYWHERE",
            "--skip-adapter",
        ]
    )

    assert code == cli_setup.EXIT_NOT_WRITTEN
    assert not (config_dir / "providers.yaml").exists()
    assert "未写入" in capsys.readouterr().out


def test_rerunning_without_a_key_keeps_the_stored_one(config_dir: Path, monkeypatch) -> None:
    """Fixing a model name must not wipe the credential — the panel's ``__UNCHANGED__`` rule."""
    monkeypatch.setenv("K1", "sk-first")
    assert _run(
        [
            "--provider-id",
            "p1",
            "--base-url",
            "https://api.example.com/v1",
            "--model",
            "old-model",
            "--api-key-env",
            "K1",
            "--skip-adapter",
        ]
    ) == cli_setup.EXIT_OK

    assert _run(
        [
            "--provider-id",
            "p1",
            "--base-url",
            "https://api.example.com/v1",
            "--model",
            "new-model",
            "--skip-adapter",
        ]
    ) == cli_setup.EXIT_OK

    text = (config_dir / "providers.yaml").read_text(encoding="utf-8")
    assert "env:K1" in text
    assert "new-model" in text


def test_a_forward_adapter_is_written(config_dir: Path) -> None:
    code = _run(
        [
            "--skip-provider",
            "--kind",
            "onebot11",
            "--mode",
            "forward",
            "--ws-url",
            "ws://127.0.0.1:3001",
            "--account-id",
            "123456789",
            "--access-token-env",
            "OB_TOKEN",
        ]
    )

    assert code == cli_setup.EXIT_OK
    text = (config_dir / "adapters.yaml").read_text(encoding="utf-8")
    assert "ws://127.0.0.1:3001" in text
    assert "env:OB_TOKEN" in text
    assert "123456789" in text


def test_reverse_without_a_token_is_refused_before_writing(config_dir: Path, capsys) -> None:
    """Startup refuses an open reverse listener; failing here is the earlier, kinder error."""
    code = _run(["--skip-provider", "--kind", "onebot11", "--mode", "reverse", "--port", "6700"])

    assert code == cli_setup.EXIT_BAD_INPUT
    assert not (config_dir / "adapters.yaml").exists()
    assert "access_token" in capsys.readouterr().err


def test_a_missing_required_value_is_bad_input_not_a_hang(config_dir: Path, capsys) -> None:
    code = _run(["--provider-id", "p1", "--skip-adapter"])

    assert code == cli_setup.EXIT_BAD_INPUT
    assert "base_url" in capsys.readouterr().err


def test_both_sections_can_be_skipped(config_dir: Path) -> None:
    code = _run(["--skip-provider", "--skip-adapter"])
    assert code == cli_setup.EXIT_OK
    # Nothing invented out of thin air.
    assert not (config_dir / "providers.yaml").exists()
    assert not (config_dir / "adapters.yaml").exists()


def test_the_summary_names_the_panel_and_the_token_command(config_dir: Path, capsys) -> None:
    _run(["--skip-provider", "--skip-adapter"])
    out = capsys.readouterr().out
    assert "/api" not in out  # a URL an operator cannot click is not a next step
    assert "soapbot start" in out
    assert "soapbot token" in out


def test_provider_patch_defaults_the_secret_to_unchanged() -> None:
    entry = cli_setup.provider_patch(
        provider_id="p1", base_url="https://x/v1", model="m", api_key=""
    )[0]
    assert entry["api_key"] == cli_setup.config_write.UNCHANGED


def test_adapter_patch_sends_only_the_keys_the_mode_uses() -> None:
    forward = cli_setup.adapter_patch(kind="onebot11", mode="forward", ws_url="ws://x:1")[0]
    assert "ws_url" in forward
    assert "host" not in forward and "port" not in forward

    reverse = cli_setup.adapter_patch(kind="onebot11", mode="reverse", host="0.0.0.0", port=6700)[0]
    assert reverse["host"] == "0.0.0.0"
    assert reverse["port"] == 6700
    assert "ws_url" not in reverse
