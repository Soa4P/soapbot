"""One fact, several copies, and nobody notices when they disagree.

Why this exists
---------------
On 2026-11-10 ``review`` became the sixth required status check. The next read-back
of the repo found the same fact stated three different ways:

* ``CONTRIBUTING.md`` said "6 个必需状态检查" at the top and "5 个检查全绿" for
  ``--admin`` fifty lines later;
* ``.github/copilot-instructions.md`` told AI assistants to "等 5 个必需检查" — a
  line that decides whether a change gets merged, and that had quietly become wrong;
* ``CHANGELOG.md`` still described the flow as "五道必需检查".

None of the existing gates could see it. ``scripts/check_test_gaps.py`` only scans
``N passed`` totals in ``README.md`` and ``docs/**``; ``tests/test_doc_test_counts.py``
scans the same set for per-file counts. ``CHANGELOG.md`` and ``.github/*.md`` were
outside both — an old blind spot, not a new one.

What this can and cannot do: it checks that each document *names* every required
check and states a count consistent with ``REQUIRED_CHECKS``. It cannot tell whether
GitHub still agrees with that constant — that needs ``gh api``, which a test must
not call, so the constant is a dated snapshot instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
COPILOT = ROOT / ".github" / "copilot-instructions.md"
CHANGELOG = ROOT / "CHANGELOG.md"

#: Read from ``gh api repos/Soa4P/soapbot/branches/master/protection/required_status_checks``
#: on 2026-11-10 (read-only; nothing was written). ``strict`` was ``true``. If the
#: repo setting changes, change this tuple and the baseline documents together: a
#: snapshot is only useful if reality drags it along.
REQUIRED_CHECKS: tuple[str, ...] = (
    "backend (ubuntu-latest, 3.12)",
    "backend (windows-latest, 3.12)",
    "frontend",
    "desktop",
    "package",
    "review",
)

#: The two spellings of one list. Both are pinned *with backticks*: a bare "desktop"
#: also matches "`desktop-bundle`" and "`required_approving_review_count`" matches
#: "review", so a substring test would stay green on a list that dropped the check.
CONTRIBUTING_SPELLING: tuple[str, ...] = (
    "`backend (ubuntu-latest, 3.12)`",
    "`backend (windows-latest, 3.12)`",
    "`frontend`",
    "`desktop`",
    "`package`",
    "`review`",
)
#: The assistant rules name the jobs the way a reader says them, not as full context
#: strings — "`backend` 两个平台" instead of naming both matrix legs.
SHORT_NAMES: tuple[str, ...] = (
    "`backend`",
    "`frontend`",
    "`desktop`",
    "`package`",
    "`review`",
)

#: ``6 个必需`` / ``六道必需`` / ``5 个检查`` — every way this repo has spelled the
#: count. The number is captured so a stale one can be named in the failure message.
STATED_COUNT = re.compile(r"([0-9]+|[一二三四五六七八九十])\s*(?:个|道)?\s*(?:必需|检查)")

_DIGITS = {word: str(index + 1) for index, word in enumerate("一二三四五六七八九十")}


def stated_counts(text: str) -> list[int]:
    """Every count the text claims, in order, in the forms this repo uses."""
    out: list[int] = []
    for match in STATED_COUNT.finditer(text):
        token = match.group(1)
        digit = _DIGITS.get(token, token)
        if digit.isdigit():
            out.append(int(digit))
    return out


def required_check_doc_problems(
    text: str, *, names: tuple[str, ...], source: str = "<memory>"
) -> list[str]:
    """Return every way this document disagrees with ``REQUIRED_CHECKS``.

    ``names`` is the spelling that document is supposed to use (full context strings
    or the short job names). ``source`` only labels the problems, so a failure points
    at a file instead of at a bare string.
    """
    out: list[str] = []
    expected = len(REQUIRED_CHECKS)

    for name in names:
        if name not in text:
            out.append(f"{source} 的必需检查名单里没有 {name}")

    counts = stated_counts(text)
    if not counts:
        out.append(f"{source} 没有写明必需检查的数量（应为 {expected} 个）")
    for count in counts:
        if count != expected:
            out.append(
                f"{source} 写着 {count} 个必需检查，实际是 {expected} 个"
                f"（{'、'.join(REQUIRED_CHECKS)}）"
            )
    return out


#: The documents that describe the *current* process, each with the spelling it must
#: use. ``CHANGELOG.md`` is history and is excluded on purpose — see
#: ``test_history_is_deliberately_not_scanned``.
CHECK_LISTS = (
    (CONTRIBUTING, CONTRIBUTING_SPELLING),
    (COPILOT, SHORT_NAMES),
)

#: A minimal correct statement built from the real context strings. Reverse cases
#: mutate this instead of the repo's files, so the rule can be shown to fail on text
#: this test controls — and so a reverse case cannot accidentally pass because the
#: word it deleted still appears somewhere else in a 130-line document.
GOOD = "6 个必需检查：" + "、".join(CONTRIBUTING_SPELLING) + "。"


def test_the_documented_check_list_matches_the_snapshot() -> None:
    for path, names in CHECK_LISTS:
        problems = required_check_doc_problems(
            path.read_text(encoding="utf-8"),
            names=names,
            source=str(path.relative_to(ROOT)),
        )
        assert problems == [], problems


def test_a_missing_context_is_reported() -> None:
    """Dropping ``review`` is the exact drift this file exists to catch: the list then
    reads fine and omits the one check nobody was waiting for.

    The full context strings are used rather than the bare word: in the real
    ``CONTRIBUTING.md`` the word "review" also appears in "AI 审查的 `review` job" and
    in ``required_approving_review_count``, so a substring test for "review" would stay
    green on a list that no longer names the check.
    """
    problems = required_check_doc_problems(
        GOOD.replace("`review`", "`types`"), names=CONTRIBUTING_SPELLING
    )
    assert any("review" in problem for problem in problems), problems


def test_an_old_count_is_reported() -> None:
    """``5 个必需检查`` was true until 2026-11-10 and is now a lie."""
    problems = required_check_doc_problems(
        GOOD.replace("6 个", "5 个"), names=CONTRIBUTING_SPELLING
    )
    assert any("写着 5 个" in problem for problem in problems), problems


def test_a_document_without_any_count_is_reported() -> None:
    """Deleting the sentence is the cheapest way to pass a gate that only looks for
    wrong numbers. Naming all six checks without saying how many still leaves the
    reader counting, so it has to fail too."""
    problems = required_check_doc_problems(
        GOOD.replace("6 个必需检查：", ""), names=CONTRIBUTING_SPELLING
    )
    assert any("没有写明必需检查的数量" in problem for problem in problems), problems


def test_the_snapshot_has_six_checks_including_review() -> None:
    """A guard on the constant itself: if someone deletes ``review`` from the tuple,
    every document problem disappears and the gate starts proving nothing."""
    assert len(REQUIRED_CHECKS) == 6
    assert "review" in REQUIRED_CHECKS
    assert len(set(REQUIRED_CHECKS)) == len(REQUIRED_CHECKS)


def test_history_is_deliberately_not_scanned() -> None:
    """Rewriting history to satisfy a gate is the wrong direction.

    A round report saying "那一轮只有五道必需检查" is accurate about that round. Scanning
    ``CHANGELOG.md`` would force it to be reworded every time the count moves — the
    same trap ``check_test_gaps.py`` removed with its round-report exemption. So the
    exclusion is asserted *and* the rule is shown to reject that phrasing: otherwise
    "excluded" and "would have passed anyway" are indistinguishable.
    """
    assert CHANGELOG not in [path for path, _ in CHECK_LISTS]

    history = "2026-11-09 那一轮只有五道必需检查，`review` 当时还在候选名单里。"
    problems = required_check_doc_problems(history, names=CONTRIBUTING_SPELLING)
    assert any("写着 5 个" in problem for problem in problems), problems
