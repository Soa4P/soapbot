"""首次登录令牌的指引必须是「能照着做」，而不是一个路径名词。

Why this exists
---------------
On a Windows cloud host an operator restarted the service, then could not find
``init_token.txt``. The docs said "open ``data/init_token.txt``" (or hard-coded
``C:\\soapbot``), the installers ended with ``(open it on this machine; it is not
printed here)``, and ``deployment.md`` described a "command to read the token"
without printing one. Nothing said that redeeming the credential deletes the file
and leaves ``init_token.redeemed``, so a restart looks like it lost the token and
no number of restarts brings it back.

The code already answers all of this: ``GET /api/auth/status`` returns
``bootstrap_state`` and the real ``bootstrap_path``, and ``token --reset`` mints a
replacement. This gate pins the *instructions*, since a correct implementation with
unusable instructions is still a locked-out operator.

The check is a pure function over a root directory so the reverse cases can prove
it fails when one piece is removed — a gate that only passes on a perfect tree and
only fails on an empty one would be indistinguishable from a gate that never ran.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

GUIDE = "docs/deploy-quickstart.md"
INSTALLERS = ("scripts/install.ps1", "deploy/windows-bootstrap.ps1")
POINTERS = ("README.md", "docs/guide.md", "docs/deployment.md", "docs/operations.md")
ALL_FILES = (GUIDE, *POINTERS, *INSTALLERS)

#: An operator on the server must be able to check the state, read the value, know
#: what a restart does, and get back in. A bare path satisfies none of these.
REQUIRED_IN_GUIDE = (
    "/api/auth/status",
    "bootstrap_state",
    "bootstrap_path",
    "Get-Content",
    "init_token.redeemed",
    "token --reset",
    "schtasks /End /TN SoapbotBot",
    "重启",
    "不是在你自己的电脑上",
    "SOAPBOT_INIT_TOKEN",
)


def guide_problems(root: Path) -> list[str]:
    """Return every way the first-login instructions would leave a reader stuck."""
    guide = root / GUIDE
    if not guide.is_file():
        return [f"{GUIDE} 不存在"]
    text = guide.read_text(encoding="utf-8")
    problems = [f"{GUIDE} 缺少 {item}" for item in REQUIRED_IN_GUIDE if item not in text]

    for relative in POINTERS:
        pointer = root / relative
        if not pointer.is_file() or "deploy-quickstart.md" not in pointer.read_text(
            encoding="utf-8"
        ):
            problems.append(f"{relative} 没有指向第一次登录指引")

    for relative in INSTALLERS:
        script = root / relative
        if not script.is_file():
            problems.append(f"{relative} 不存在")
            continue
        body = script.read_text(encoding="utf-8")
        if "init_token.txt" not in body:
            problems.append(f"{relative} 没给出令牌文件路径")
        if "notepad" not in body:
            problems.append(f"{relative} 没给出可直接粘贴的打开命令")
        if "ON THIS SERVER" not in body:
            problems.append(f"{relative} 没说清要在哪台机器上找")
        # The old hint was the reported problem: "this machine" is ambiguous when the
        # operator is sitting at a laptop and the install is on a cloud host.
        if "open it on this machine" in body or "not printed here" in body:
            problems.append(f"{relative} 还在用含糊的旧提示")
        # A service installer must not echo the credential into a console transcript.
        # `Get-Content $envFile` reads .env during setup and is harmless; only a line
        # that explicitly reads the token file leaks it. Same rule as
        # tests/test_install_scripts.py, so the two gates cannot disagree.
        if re.search(r"Get-Content[^\n]*init_token", body) or "cli token" in body:
            problems.append(f"{relative} 会把令牌值带进终端")
    return problems


def _copy(root: Path) -> None:
    for relative in ALL_FILES:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_the_first_login_guide_is_actionable() -> None:
    assert guide_problems(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "needle", "expected"),
    [
        (GUIDE, "bootstrap_state", "bootstrap_state"),
        (GUIDE, "Get-Content", "Get-Content"),
        (GUIDE, "token --reset", "token --reset"),
        (GUIDE, "不是在你自己的电脑上", "不是在你自己的电脑上"),
        ("scripts/install.ps1", "notepad", "没给出可直接粘贴的打开命令"),
        ("deploy/windows-bootstrap.ps1", "ON THIS SERVER", "没说清要在哪台机器上找"),
        ("docs/guide.md", "deploy-quickstart.md", "没有指向"),
        ("README.md", "docs/deploy-quickstart.md", "没有指向"),
    ],
)
def test_removing_one_piece_makes_the_gate_fail(
    tmp_path: Path, relative: str, needle: str, expected: str
) -> None:
    """Each individual regression is caught, not just a wholesale deletion."""
    _copy(tmp_path)
    path = tmp_path / relative
    assert needle in path.read_text(encoding="utf-8"), "反向用例自身失去了意义"
    path.write_text(
        path.read_text(encoding="utf-8").replace(needle, ""), encoding="utf-8"
    )
    problems = guide_problems(tmp_path)
    assert any(expected in problem for problem in problems), (relative, needle, problems)


def test_the_old_ambiguous_hint_is_rejected(tmp_path: Path) -> None:
    """The exact wording the operator complained about must not come back."""
    _copy(tmp_path)
    path = tmp_path / "scripts" / "install.ps1"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "ON THIS SERVER, not on your own PC", "open it on this machine"
        ),
        encoding="utf-8",
    )
    problems = guide_problems(tmp_path)
    assert any("还在用含糊的旧提示" in problem for problem in problems)
    assert any("没说清要在哪台机器上找" in problem for problem in problems)
