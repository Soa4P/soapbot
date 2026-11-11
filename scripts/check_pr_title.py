#!/usr/bin/env python3
"""Reject PR titles that do not follow this repository's own naming rule.

Why a script instead of a paragraph
-----------------------------------
``CONTRIBUTING.md`` says a PR title is one line of Chinese in the form
``动作: 对象`` (``新增地图: ze_x``, ``修复: Windows 重启后保留登录令牌``). A rule that
only exists in prose is a rule that gets skipped the first time someone is in a hurry,
and reviewing the title by hand is exactly the step that gets dropped when the diff is
large.

This is a format check, not a taste check: it cannot tell whether the title describes
the change. It only refuses the two things that make titles hard to scan — a
Conventional-Commits prefix (``feat:`` / ``fix:``) that this repository never agreed to,
and a colon with nothing after it.

Exit codes: 0 = acceptable, 1 = rejected, 2 = no title was supplied at all (a wiring
mistake, not a bad title; CI should fail loudly on it rather than pass silently).
"""

from __future__ import annotations

import argparse
import os
import re
import sys

#: Prefixes from Conventional Commits. They are not wrong in general; they are wrong
#: here, because the rest of this repository's history and its PR template use the
#: Chinese form, and mixing the two makes the list unreadable at a glance.
CONVENTIONAL = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|ci|build|perf|style|revert)"
    r"(\([^)]*\))?!?:",
    re.IGNORECASE,
)

#: ``动作: 对象``. The action is 2–12 Chinese characters; the separator may be the
#: half-width colon used by the real examples, or the full-width one a Chinese IME
#: produces; the object must contain at least one non-space character.
TITLE = re.compile(r"^[\u4e00-\u9fff]{2,12}\s*[:：]\s*\S")

MAX_LENGTH = 80


def problems(title: str) -> list[str]:
    """Every reason this title is unusable. Empty means acceptable."""
    text = (title or "").strip()
    if not text:
        return ["标题为空"]
    out: list[str] = []
    if len(text) > MAX_LENGTH:
        out.append(f"标题过长（{len(text)} > {MAX_LENGTH} 字符）")
    if CONVENTIONAL.match(text):
        out.append("不要用 feat:/fix: 这类英文前缀，改成「动作: 对象」")
    if not TITLE.match(text):
        out.append("格式应为「动作: 对象」，例如「修复: Windows 重启后保留登录令牌」")
    return out


def main(argv: list[str] | None = None) -> int:
    # CI runs this on Windows runners too, where the console code page turns the
    # Chinese reason text into replacement characters. The message is the whole value
    # of a failing check, so pin the encoding rather than hope for the locale.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Check a PR title against 动作: 对象")
    parser.add_argument("--title", default=None, help="PR title; defaults to $PR_TITLE")
    args = parser.parse_args(argv)

    title = args.title if args.title is not None else os.environ.get("PR_TITLE", "")
    if not (title or "").strip():
        print("no title supplied (pass --title or set PR_TITLE)", file=sys.stderr)
        return 2

    out = problems(title)
    if out:
        for reason in out:
            print(f"[title] {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
