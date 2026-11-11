"""The PR title rule from ``CONTRIBUTING.md`` must be executable.

Two failure modes are covered by the positive cases and three by the negative ones:
the rule has to accept what the repository actually writes (Chinese action, either
colon width), reject the Conventional-Commits form that the docs never agreed to, and
not mistake "no title supplied" for "title is fine" — a wiring mistake in CI must fail
loudly, not pass because the variable was empty.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_pr_title.py"


def _run(*args: str, title: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PR_TITLE"}
    # The child writes Chinese reasons; without this the Windows console code page
    # turns them into replacement characters before the test can look at them.
    env["PYTHONIOENCODING"] = "utf-8"
    if title is not None:
        env["PR_TITLE"] = title
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_a_chinese_action_with_a_half_width_colon_is_accepted() -> None:
    result = _run("--title", "新增安全加固: 语义授权取舍与四层门控")
    assert result.returncode == 0, result.stderr


def test_a_full_width_colon_from_a_chinese_ime_is_accepted() -> None:
    result = _run("--title", "修复：Windows 重启后保留登录令牌")
    assert result.returncode == 0, result.stderr


def test_a_conventional_commit_prefix_is_rejected() -> None:
    result = _run("--title", "feat: semantic authorisation")
    assert result.returncode == 1
    assert "前缀" in result.stderr


def test_an_empty_object_is_rejected() -> None:
    result = _run("--title", "修复:   ")
    assert result.returncode == 1


def test_an_overlong_title_is_rejected() -> None:
    result = _run("--title", "修复: " + "很长的描述" * 20)
    assert result.returncode == 1
    assert "过长" in result.stderr


def test_the_title_can_arrive_through_the_environment() -> None:
    # CI passes ``github.event.pull_request.title`` as an env var rather than through a
    # quoted shell argument: the same command then works on bash and on pwsh runners.
    result = _run(title="修改配置: 面板默认端口")
    assert result.returncode == 0, result.stderr


def test_a_missing_title_fails_loudly() -> None:
    result = _run()
    assert result.returncode == 2
    assert "no title" in result.stderr
