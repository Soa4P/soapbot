"""The semantic-authorisation verdict document must stay honest.

Why a test for a document
-------------------------
An audit table is only as good as its weakest row. The failure mode here is not a typo:
it is quietly rewriting "不适用" into "已覆盖" so a checklist looks green, or citing a
file that was renamed three rounds ago. Both produce a document that reads as evidence
and is not.

So the document is parsed as a contract, not admired as prose:

* six tables with a fixed header and exactly four allowed verdicts;
* every row cites at least one path that exists;
* the explicit "不适用 / 未知" id lists agree with the verdict column;
* entities that do not exist in this repository are never described as passed, and a
  static scan proves they genuinely have no runtime entity.

Nothing here starts a service, touches the database, or imports application code.
A read-only scan of source text plus one Markdown file is enough, and it is deterministic.

The reverse cases matter as much as the forward ones: a rule that silently stops
matching reports "0 problems" for the worst possible reason. Each tampering case below
must make the parser complain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "semantic-authorization.md"
SRC = ROOT / "src" / "soapbot"

HEADER = "| 条目 | 判定 | 证据 | 残余风险 |"
SELF_REFERENCE = "tests/test_semantic_authorization_review.py"
TABLE_COUNT = 6
VERDICTS = ("已覆盖", "部分覆盖", "不适用", "未知")
MINIMUM_ROWS = 28

#: Entities the checklist assumes but this single-process bot does not have. Kept as
#: exact identifiers so the absence assertion cannot be satisfied by "we never used
#: that *word* in a comment". ``dormant`` is deliberately excluded: it appears twice in
#: prose comments (a dormant DB column, dormant QQ maintenance) but is no idle-agent
#: mechanism. ``settle`` is excluded because ``Promise.allSettled`` and
#: ``_settle_stderr`` are unrelated homonyms.
ABSENT_IDENTIFIERS = (
    "mandate",
    "settlement",
    "ensemble",
    "trifecta",
    "broker",
    "credential_decay",
    "jurisdiction",
    "post_quantum",
    "calibration",
    "semantic_frame",
)

ROW_ID = re.compile(r"^([A-F]\d+)\b")
#: A backticked repository-relative path, optionally with a line range. Restricting the
#: suffix keeps ordinary prose in backticks (symbol names, env vars) out of the check.
EVIDENCE_PATH = re.compile(
    r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|md|json|txt|sh|ps1|yml|yaml|ts|vue|bat))`"
)
DECLARED_IDS = re.compile(r"判为「(不适用|未知)」的 \d+ 条主张：([^\n。]+)")
_ENTITY = "|".join(re.escape(word) for word in ABSENT_IDENTIFIERS)
FORBIDDEN_PASSED = re.compile(
    rf"(?:{_ENTITY})[^\n|]{{0,48}}(?:已通过|已覆盖|verified|passed)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Row:
    ident: str
    verdict: str
    evidence: str
    residual: str


def parse_rows(text: str) -> list[Row]:
    """Data rows from all six verdict tables.

    A row is a four-cell line whose first cell starts with an id like ``A1``. Header,
    separator, and the unrelated four-verdict glossary table all fail that test.
    """
    rows: list[Row] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 4:
            continue
        match = ROW_ID.match(cells[0])
        if match is None:
            continue
        rows.append(Row(match.group(1), cells[1], cells[2], cells[3]))
    return rows


def declared_ids(text: str, verdict: str) -> list[str]:
    for match in DECLARED_IDS.finditer(text):
        if match.group(1) == verdict:
            return re.findall(r"[A-F]\d+", match.group(2))
    return []


def problems(text: str) -> list[str]:
    """Every contract violation in a rendered copy of the verdict document.

    Prefixed so a test can assert on one class of violation, and so the reverse cases
    can show which rule caught the tampering.
    """
    found: list[str] = []

    if text.count(HEADER) != TABLE_COUNT:
        found.append(f"header: expected {TABLE_COUNT} verbatim table headers")
    for verdict in VERDICTS:
        if verdict not in text:
            found.append(f"header: verdict {verdict!r} is not defined")

    rows = parse_rows(text)
    if len(rows) < MINIMUM_ROWS:
        found.append(f"rows: only {len(rows)} verdict rows, floor is {MINIMUM_ROWS}")
    ids = [row.ident for row in rows]
    if len(ids) != len(set(ids)):
        found.append("rows: duplicate row ids")

    for row in rows:
        if row.verdict not in VERDICTS:
            found.append(f"verdict: {row.ident} uses {row.verdict!r}")
        if not row.residual:
            found.append(f"verdict: {row.ident} has no residual risk")
        paths = EVIDENCE_PATH.findall(row.evidence)
        if not paths:
            found.append(f"path: {row.ident} cites no repository path")
        for path in paths:
            if not (ROOT / path).is_file():
                found.append(f"path: {row.ident} cites missing {path}")
        if row.verdict == "不适用" and SELF_REFERENCE not in row.evidence:
            found.append(f"na: {row.ident} must cite the absence assertion itself")

    na = declared_ids(text, "不适用")
    unknown = declared_ids(text, "未知")
    if not na or not unknown:
        found.append("ids: the declared 不适用 / 未知 id lists are missing")
    else:
        actual_na = {row.ident for row in rows if row.verdict == "不适用"}
        actual_unknown = {row.ident for row in rows if row.verdict == "未知"}
        if set(na) != actual_na:
            found.append("ids: 不适用 list disagrees with the verdict column")
        if set(unknown) != actual_unknown:
            found.append("ids: 未知 list disagrees with the verdict column")

    for match in FORBIDDEN_PASSED.finditer(text):
        found.append(f"passed: {match.group(0)[:60]!r}")

    return found


def document() -> str:
    return DOC.read_text(encoding="utf-8")


def test_verdict_table_headers_are_intact() -> None:
    text = document()
    assert text.count(HEADER) == TABLE_COUNT
    assert not [p for p in problems(text) if p.startswith("header:")]


def test_all_four_verdicts_are_defined_and_used() -> None:
    text = document()
    rows = parse_rows(text)
    for verdict in VERDICTS:
        assert verdict in text, f"{verdict} is not defined in the verdict glossary"
    assert len(rows) >= MINIMUM_ROWS
    assert {row.verdict for row in rows} <= set(VERDICTS)
    assert all(row.residual for row in rows)
    assert not [p for p in problems(text) if p.startswith(("verdict:", "rows:"))]


def test_every_row_cites_a_real_repository_path() -> None:
    for row in parse_rows(document()):
        paths = EVIDENCE_PATH.findall(row.evidence)
        assert paths, f"{row.ident} cites no path"
        missing = [path for path in paths if not (ROOT / path).is_file()]
        assert not missing, f"{row.ident} cites missing files: {missing}"


def test_declared_na_and_unknown_ids_match_the_table() -> None:
    text = document()
    rows = parse_rows(text)
    assert set(declared_ids(text, "不适用")) == {
        row.ident for row in rows if row.verdict == "不适用"
    }
    assert set(declared_ids(text, "未知")) == {
        row.ident for row in rows if row.verdict == "未知"
    }
    for row in rows:
        if row.verdict == "不适用":
            assert SELF_REFERENCE in row.evidence, (
                f"{row.ident} must point at the absence assertion itself"
            )
    assert not [p for p in problems(text) if p.startswith(("ids:", "na:"))]


def test_no_absent_entity_is_written_as_passed() -> None:
    assert not [p for p in problems(document()) if p.startswith("passed:")]


def test_the_forbidden_pattern_is_not_vacuous() -> None:
    """A regex that never matches would make the previous test green for free."""
    assert FORBIDDEN_PASSED.search("mandate 链路已通过") is not None
    assert FORBIDDEN_PASSED.search("F26 ensemble verified") is not None
    assert FORBIDDEN_PASSED.search("mandate 链路尚未验证") is None


def test_absent_identifiers_have_no_runtime_entity() -> None:
    """「不适用」is a fact about the runtime code, not a claim in prose.

    Only ``src/soapbot`` is scanned. Tests are deliberately outside the scope: this
    file and ``test_optimization_triage.py`` both have to quote the identifier list in
    order to assert its absence, so including tests would mean testing our own
    vocabulary. A runtime entity would live under ``src/``, which is what matters.
    """
    files = list(SRC.rglob("*.py"))
    assert len(files) > 100, "the scan must cover the real source tree"
    corpus = {
        path: path.read_text(encoding="utf-8", errors="replace") for path in files
    }
    for word in ABSENT_IDENTIFIERS:
        hits = [
            str(path.relative_to(ROOT))
            for path, source in corpus.items()
            if re.search(re.escape(word), source, re.IGNORECASE)
        ]
        assert not hits, f"{word} unexpectedly has a runtime entity: {hits}"


def test_tampering_with_a_verdict_is_detected() -> None:
    text = document()
    needle = "| F26 Agent-Ensemble / Ensemble Trifecta | 不适用 |"
    assert needle in text
    tampered = text.replace(needle, needle.replace("不适用", "已覆盖"))
    assert any(p.startswith(("ids:", "passed:")) for p in problems(tampered))


def test_an_invented_evidence_path_is_detected() -> None:
    text = document()
    needle = "`src/soapbot/plugins/attestation.py`"
    assert needle in text
    tampered = text.replace(needle, "`src/soapbot/plugins/does-not-exist.py`")
    assert any(p.startswith("path:") for p in problems(tampered))


def test_broken_header_and_deleted_row_are_detected() -> None:
    text = document()
    broken = text.replace(HEADER, "| 条目 | 结论 | 证据 | 残余风险 |")
    assert any(p.startswith("header:") for p in problems(broken))

    without_a1 = "\n".join(
        line for line in text.splitlines() if not line.startswith("| A1 ")
    )
    detected = problems(without_a1)
    assert any(p.startswith(("rows:", "ids:")) for p in detected)
