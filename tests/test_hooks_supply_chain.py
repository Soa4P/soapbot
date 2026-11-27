"""Developer-machine supply chain: the hooks that guard the gates are guarded too.

Two properties, both from audit S-DEP-20:

* **pre-commit revs are SHAs, not tags.** A tag is mutable, and a hook repo is exactly
  the kind of thing a developer forgets they execute on every commit. The repository
  already pins every CI `uses:` to a commit; this file follows the same rule.
* **pre-push runs the committed scanner, not the working-tree copy.** Whatever modified
  the checkout also modified the script a naive hook would execute at the moment bytes
  leave the machine. Piping `git show HEAD:…` through the interpreter pins the scan to
  the reviewed version; the versioned hook lives in `scripts/hooks/pre-push` so the
  behaviour is reviewable, not just installed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".pre-commit-config.yaml"
HOOK = ROOT / "scripts" / "hooks" / "pre-push"


def test_pre_commit_revs_are_commit_shas_with_the_tag_commented() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    revs = re.findall(r"rev:\s*(\S+)", text)
    assert revs, "no hooks configured — this test would silently pass on removal"
    for rev in revs:
        assert re.fullmatch(r"[0-9a-f]{40}", rev), f"rev must be a 40-hex SHA, got {rev!r}"
    for version in re.findall(r"# (v[\d.]+)\s*$", text, flags=re.MULTILINE):
        assert version, "the human-readable tag stays in the comment for upgrades"


def test_the_versioned_pre_push_hook_scans_the_committed_scanner() -> None:
    text = HOOK.read_text(encoding="utf-8")
    assert "git show HEAD:scripts/check_secrets.py" in text
    # And it must not fall back to executing the working-tree file.
    assert "check_secrets.py --pre-push" not in text, (
        "钩子必须跑提交版扫描器，不是工作区副本"
    )


def test_the_hook_feeds_git_ref_data_not_a_pipe() -> None:
    """The scanner reads the push's ref data from stdin.

    The first version piped `git show … | python -`, which replaced the hook's stdin —
    the scanner saw no ref data and refused every push. This was committed and only
    caught on a real push, because both static assertions passed on either shape. The
    temp-file form is the contract: materialise the committed script, keep stdin.
    """
    text = HOOK.read_text(encoding="utf-8")
    assert 'git show HEAD:scripts/check_secrets.py > "$TMP"' in text
    assert '"$PY" "$TMP" --pre-push' in text
    assert "| \"$PY\" - --pre-push" not in text, "管道会顶掉钩子的 stdin（实测拒绝一切 push）"


def test_the_installed_hook_matches_the_versioned_one() -> None:
    """A hook that drifted from the reviewed copy is a second, unaudited hook."""
    installed = ROOT / ".git" / "hooks" / "pre-push"
    if not installed.is_file():
        return  # nothing installed yet; the versioned file above is the contract
    assert installed.read_text(encoding="utf-8") == HOOK.read_text(encoding="utf-8"), (
        ".git/hooks/pre-push 与 scripts/hooks/pre-push 不一致——以版本化文件为准重新安装"
    )
