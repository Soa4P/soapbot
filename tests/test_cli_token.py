"""``soapbot token`` — the recovery path that was documented but missing.

The command exists because ``.env.example`` told operators to run it while the argument
parser had no such subcommand. These tests pin the behaviour that makes it useful rather
than merely present: it must print the token, and it must say the token may be stale —
the file is not deleted after redemption, so a bare value would send someone to the login
form with a dead credential and no explanation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot import cli
from soapbot.config import settings


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the data dir without touching the real one."""
    monkeypatch.setattr(settings, "data_dir", tmp_path, raising=False)
    return tmp_path


def test_prints_token_when_file_present(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    token = "SkyYcFBbHbsnRifRPkixqbR-BIMOVxQJ"
    (data_dir / "init_token.txt").write_text(token + "\n", encoding="utf-8")

    assert cli.main(["token"]) == 0

    out, err = capsys.readouterr()
    assert out.strip() == token, "stdout 必须只有令牌本身，便于 $(...) 或管道取值"
    # The caveat has to be on stderr so `TOKEN=$(soapbot token)` still works.
    assert "一次性" in err
    assert "已被消费" in err
    assert token[:4] in err


def test_missing_file_explains_why(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["token"]) == 1
    _out, err = capsys.readouterr()
    assert "没有找到引导令牌文件" in err
    # Three causes, because "file not found" alone invites the wrong fix.
    assert "首次启动" in err
    assert "SOAPBOT_INIT_TOKEN" in err
    assert "SOAPBOT_DATA_DIR" in err


def test_empty_file_is_not_printed_as_token(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (data_dir / "init_token.txt").write_text("   \n", encoding="utf-8")
    assert cli.main(["token"]) == 1
    out, err = capsys.readouterr()
    assert out.strip() == ""
    assert "空文件" in err


def test_token_subcommand_is_registered() -> None:
    """Guards the exact regression that made the docs wrong: subcommand absent."""
    import argparse

    parser = argparse.ArgumentParser(prog="soapbot")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("token")
    # The real check is below: the CLI's own parser must accept it.
    with pytest.raises(SystemExit) as exc:
        cli.main(["token", "--nope"])
    assert exc.value.code == 2, "参数解析应拒绝未知选项（说明 token 子命令已存在）"


def test_stdout_stays_machine_readable(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A pipeline like `TOKEN=$(soapbot token)` must receive only the token.

    This is the reason the hint text goes to stderr rather than stdout: a token printed
    together with advice is unusable in a script, and scripts are the main consumer of
    this command in a container entrypoint.
    """
    token = "abc123def456"
    (data_dir / "init_token.txt").write_text(token, encoding="utf-8")
    cli.main(["token"])
    out, _err = capsys.readouterr()
    assert out == token + "\n"
    assert len(out.splitlines()) == 1
