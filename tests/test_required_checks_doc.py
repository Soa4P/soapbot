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

Why the checks are anchored to a paragraph
------------------------------------------
The first version of this gate searched the whole document for each name. Deleting
``\\`desktop\\```, ``\\`frontend\\``` or ``\\`review\\``` from the actual list in
``CONTRIBUTING.md`` still passed, because each word also appears elsewhere in the same
file (``review`` six times) — a gate that cannot fail on the change it was written for.
The rules below are therefore scoped: the count and the full list must sit in the *same*
paragraph, and a sentence that claims "these are all green, so it merges" must name
exactly the required checks.
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

#: Paragraph breaks, as both documents write them. A list is one paragraph even when it
#: is wrapped over two source lines, so this is deliberately *not* line-based.
PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")

#: A clause promising that green CI is what allows a merge. Whatever it names, it is
#: describing the required set, so the names it lists have to be that set.
MERGE_CLAIM = "全绿"

#: Sentence boundaries inside a paragraph. Scoping rule 3 to a clause, not a paragraph,
#: is what lets a document say "these six 全绿 ... `types` 是咨询性的" without the
#: advisory mention being read as part of the required list. Line breaks are *not*
#: boundaries here: prose wraps, and a sentence split across two source lines would
#: otherwise be judged by its first half only.
CLAUSE_BREAK = re.compile(r"[。；！？]")

#: A line that starts a new list item or heading, i.e. genuinely starts a new sentence
#: even without a full stop. Anything else is a wrapped continuation of the line above.
LINE_START = re.compile(r"^\s*(?:[0-9]+[.)]|[-*+]\s|\||#)")

#: Job names without their contexts, so ``backend`` and
#: ``backend (ubuntu-latest, 3.12)`` are the same job for the "which are listed" test.
LEAF_NAMES: tuple[str, ...] = tuple(check.split(" (")[0] for check in REQUIRED_CHECKS)

#: Jobs that exist in ``.github/workflows/ci.yml`` but are *not* required: ``types`` is
#: advisory and ``desktop-bundle`` is triggered on demand. Listing one of these as a
#: merge condition is wrong in the same way as omitting a required one.
NON_REQUIRED_JOBS: tuple[str, ...] = ("types", "desktop-bundle", "release")

_BACKTICKED = re.compile(r"`([^`]+)`")


def stated_counts(text: str) -> list[int]:
    """Every count the text claims, in order, in the forms this repo uses."""
    out: list[int] = []
    for match in STATED_COUNT.finditer(text):
        token = match.group(1)
        digit = _DIGITS.get(token, token)
        if digit.isdigit():
            out.append(int(digit))
    return out


def paragraphs(text: str) -> list[str]:
    return [part for part in PARAGRAPH_BREAK.split(text) if part.strip()]


def clauses(block: str) -> list[str]:
    """Split one paragraph into sentences, un-wrapping first.

    Rule 3 originally split on ``\\n`` as well, and `CONTRIBUTING.md` immediately showed
    why that is wrong: the sentence listing the six checks wrapped after ``desktop``, so
    the half that mentioned ``全绿`` looked like a list of three. A wrapped continuation
    is joined back; only a new list item, table row or heading starts a new sentence.
    """
    joined: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        if joined and not LINE_START.match(line):
            joined[-1] += line.strip()
        else:
            joined.append(line.strip())
    out: list[str] = []
    for line in joined:
        out.extend(part.strip() for part in CLAUSE_BREAK.split(line) if part.strip())
    return out


def required_check_doc_problems(
    text: str, *, names: tuple[str, ...], source: str = "<memory>"
) -> list[str]:
    """Return every way this document disagrees with ``REQUIRED_CHECKS``.

    ``names`` is the spelling that document is supposed to use (full context strings
    or the short job names). ``source`` only labels the problems, so a failure points
    at a file instead of at a bare string.

    Three rules, all paragraph-scoped. The scoping is the point: an earlier version
    searched the whole file, so dropping ``desktop`` from the real list still passed
    because the word appears again twenty lines later.
    """
    out: list[str] = []
    expected = len(REQUIRED_CHECKS)
    blocks = paragraphs(text)

    # 1. Somewhere there must be one paragraph that states the count *and* names every
    #    check. Separating them is how "6 个" survives a list that lost an entry.
    #    The message names the best candidate paragraph's gaps rather than saying
    #    "not found": someone who deleted one bullet needs to know which bullet.
    anchors = [block for block in blocks if stated_counts(block)]
    if anchors:
        best = max(anchors, key=lambda block: sum(n in block for n in names))
        for name in names:
            if name not in best:
                out.append(
                    f"{source} 中写明数量的那一段没有 {name}"
                    f"（名单和数量必须同段，否则删掉一项只剩全文别处还能搜到）"
                )

    # 2. Every stated count is the real count.
    counts = stated_counts(text)
    if not counts:
        out.append(f"{source} 没有写明必需检查的数量（应为 {expected} 个）")
    for count in counts:
        if count != expected:
            out.append(
                f"{source} 写着 {count} 个必需检查，实际是 {expected} 个"
                f"（{'、'.join(REQUIRED_CHECKS)}）"
            )

    # 3. A "these are green, so merge" clause must list exactly the required jobs.
    #    `CONTRIBUTING.md` said "backend 两个平台 + frontend + types + desktop 全绿" —
    #    it named an advisory check and omitted `package` and `review`. No count is
    #    involved, so rules 1 and 2 never looked at it.
    for block in blocks:
        for clause in clauses(block):
            if MERGE_CLAIM not in clause:
                continue
            # Normalise the full context strings down to the job name, so a document
            # that says `backend (ubuntu-latest, 3.12)` and one that says `backend`
            # are judged the same way.
            tokens = [token.split(" (")[0] for token in _BACKTICKED.findall(clause)]
            listed = {token for token in tokens if token in LEAF_NAMES}
            if not listed:
                continue
            extra = sorted({token for token in tokens if token in NON_REQUIRED_JOBS})
            absent = sorted(set(LEAF_NAMES) - listed)
            if absent or extra:
                detail = []
                if absent:
                    detail.append(f"漏了 {'、'.join(f'`{n}`' for n in absent)}")
                if extra:
                    detail.append(f"多了不需要的 {'、'.join(f'`{n}`' for n in extra)}")
                out.append(
                    f"{source} 中描述「{MERGE_CLAIM}」的句子把 "
                    f"{'、'.join(f'`{n}`' for n in sorted(listed))} 当成合并条件，"
                    f"但{'；'.join(detail)}"
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


def _drop_from_counted_paragraph(text: str, name: str) -> str:
    """Remove ``name`` from the paragraph that carries the count, leaving the rest."""
    for block in paragraphs(text):
        if stated_counts(block) and name in block:
            return text.replace(block, block.replace(name, "", 1), 1)
    raise AssertionError(f"找不到含 {name} 且写了数量的段落，用例需要更新")


def test_deleting_any_one_bullet_from_the_real_list_fails() -> None:
    """The bug this replaces: the gate searched the whole file.

    Deleting ``\\`desktop\\```, ``\\`frontend\\``` or ``\\`review\\``` from the actual list
    in ``CONTRIBUTING.md`` passed, because each word also appears elsewhere in the same
    file — ``review`` six times. A gate that cannot fail on the edit it exists for is
    worse than no gate: it certifies the drift. So this mutates the *real* document, one
    bullet at a time, and requires a failure naming the dropped check each time.
    """
    text = CONTRIBUTING.read_text(encoding="utf-8")
    for name in CONTRIBUTING_SPELLING:
        mutated = _drop_from_counted_paragraph(text, name)
        assert mutated != text, f"{name} 没被删掉，用例没测到东西"
        problems = required_check_doc_problems(
            mutated, names=CONTRIBUTING_SPELLING, source="CONTRIBUTING.md"
        )
        assert problems, f"删掉 {name} 却没有任何报错"
        assert any(name in problem for problem in problems), (name, problems)


def test_a_merge_claim_naming_the_wrong_jobs_fails() -> None:
    """The sentence that was actually wrong, verbatim from ``CONTRIBUTING.md`` before
    this gate grew rule 3: it names an advisory check and omits two required ones, and
    it states no count, so rules 1 and 2 never look at it."""
    stale = (
        "3. **合并看 CI**。`backend` 两个平台 + `frontend` + `types` + `desktop` 全绿。\n"
        "   2026-11-08 的 `#18` 在 Windows 上红过一次。"
    )
    problems = required_check_doc_problems(
        stale, names=CONTRIBUTING_SPELLING, source="CONTRIBUTING.md"
    )
    assert any("漏了" in problem for problem in problems), problems
    assert any("`types`" in problem for problem in problems), problems


def test_a_merge_claim_split_across_a_line_break_is_still_read_whole() -> None:
    """Prose wraps. Splitting clauses on ``\\n`` made the sentence that lists the six
    checks look like a sentence listing three, because the wrap fell after ``desktop``."""
    wrapped = (
        "6 个必需检查：`backend (ubuntu-latest, 3.12)`、`backend (windows-latest, 3.12)`、\n"
        "`frontend`、`desktop`、`package`、`review` 全绿。"
    )
    problems = required_check_doc_problems(
        wrapped, names=CONTRIBUTING_SPELLING, source="CONTRIBUTING.md"
    )
    assert problems == [], problems


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
