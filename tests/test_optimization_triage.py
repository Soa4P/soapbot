"""The optimisation triage document is a contract, not an opinion.

Why this exists
---------------
A "we looked at the checklist" document is easy to let drift: a row silently changes
from 不适用 to 已通过, a cited file gets renamed, or the summary counts stop matching the
table. Every one of those makes the document read as evidence while saying something
nobody verified.

So the table is parsed. Four buckets, contiguous ids, a real path per row, summary
counts that agree with the rows, and a static scan proving the entities we call
"不适用" genuinely have no runtime object. The reverse cases are the point: each kind
of tampering must produce a problem instead of a quiet green.

Nothing here imports application code, starts a service, or touches the database.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "optimization-triage.md"
SRC = ROOT / "src" / "soapbot"

HEADER = "| # | 条目（简写） | 取舍 | 证据与理由 |"
BUCKETS = ("该落实", "没有用", "不适用", "已具备")
EXPECTED_ROWS = 26

#: Entities called out as 不适用 in the checklist. They must not acquire a runtime
#: object while this document still says they have none. ``dormant`` is excluded on
#: purpose: two prose comments use it but there is no idle-agent mechanism.
ABSENT_ENTITIES = (
    "mandate",
    "settlement",
    "ensemble",
    "trifecta",
    "broker",
    "jurisdiction",
    "post_quantum",
    "credential_decay",
    "calibration",
    "semantic_frame",
)

ROW_ID = re.compile(r"^\d{2}$")
EVIDENCE_PATH = re.compile(
    r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\."
    r"(?:py|md|json|txt|sh|ps1|yml|yaml|ts|vue|bat|rs|toml|mjs))"
    r"(?::[\d,\-]+)?`"
)
SUMMARY = re.compile(
    r"\*\*汇总\*\*：(\d+) 条中，该落实 (\d+)、没有用 (\d+)、不适用 (\d+)、已具备 (\d+)"
)
PASSED_WORDING = re.compile(r"已通过|已覆盖|verified|passed", re.IGNORECASE)


@dataclass(frozen=True)
class Row:
    ident: str
    verdict: str
    evidence: str

    @property
    def bucket(self) -> str:
        """The first bucket named, before any parenthesised qualifier."""
        return self.verdict.split("（")[0].split("/")[0].strip()


def parse_rows(text: str) -> list[Row]:
    rows: list[Row] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 4 or not ROW_ID.match(cells[0]):
            continue
        rows.append(Row(cells[0], cells[2], cells[3]))
    return rows


def problems(text: str) -> list[str]:
    """Every contract violation in a rendered copy of the triage document."""
    found: list[str] = []

    if HEADER not in text:
        found.append("header: the four-column table header is missing")
    for bucket in BUCKETS:
        if bucket not in text:
            found.append(f"header: bucket {bucket!r} is not defined")

    rows = parse_rows(text)
    if len(rows) != EXPECTED_ROWS:
        found.append(f"rows: {len(rows)} rows, expected {EXPECTED_ROWS}")
    ids = [row.ident for row in rows]
    if ids != [f"{n:02d}" for n in range(1, len(ids) + 1)]:
        found.append("rows: ids are not contiguous from 01")

    for row in rows:
        if row.bucket not in BUCKETS:
            found.append(f"verdict: {row.ident} uses {row.verdict!r}")
        if row.bucket in ("没有用", "不适用") and PASSED_WORDING.search(row.evidence):
            found.append(f"passed: {row.ident} describes an absent entity as passed")
        paths = EVIDENCE_PATH.findall(row.evidence)
        if not paths:
            found.append(f"path: {row.ident} cites no repository path")
        for path in paths:
            if not (ROOT / path).is_file():
                found.append(f"path: {row.ident} cites missing {path}")

    match = SUMMARY.search(text)
    if match is None:
        found.append("summary: the four bucket counts are missing")
    else:
        total, *counts = (int(part) for part in match.groups())
        actual = Counter(row.bucket for row in rows)
        if total != len(rows):
            found.append("summary: the stated total disagrees with the table")
        for bucket, claimed in zip(BUCKETS, counts, strict=True):
            if claimed != actual[bucket]:
                found.append(
                    f"summary: {bucket} claims {claimed}, table has {actual[bucket]}"
                )

    if "重复粘贴" not in text:
        found.append("findings: the duplicate-paste observation is missing")
    if "## 2. 本地未推送检查结论" not in text:
        found.append("findings: the local-unpushed conclusion is missing")
    if "git rev-list --count origin/master..HEAD" not in text:
        found.append("findings: the unpushed-commit evidence is missing")

    return found


def document() -> str:
    return DOC.read_text(encoding="utf-8")


def test_table_header_and_contiguous_row_ids() -> None:
    text = document()
    assert HEADER in text
    rows = parse_rows(text)
    assert len(rows) == EXPECTED_ROWS
    assert [row.ident for row in rows] == [
        f"{n:02d}" for n in range(1, EXPECTED_ROWS + 1)
    ]


def test_all_four_buckets_are_defined_and_the_only_ones_used() -> None:
    text = document()
    for bucket in BUCKETS:
        assert bucket in text
    assert {row.bucket for row in parse_rows(text)} == set(BUCKETS)


def test_summary_counts_match_the_table() -> None:
    text = document()
    match = SUMMARY.search(text)
    assert match is not None
    total, *counts = (int(part) for part in match.groups())
    actual = Counter(row.bucket for row in parse_rows(text))
    assert total == EXPECTED_ROWS
    assert dict(zip(BUCKETS, counts, strict=True)) == {b: actual[b] for b in BUCKETS}
    assert not [p for p in problems(text) if p.startswith("summary:")]


def test_every_row_cites_a_real_repository_path() -> None:
    for row in parse_rows(document()):
        paths = EVIDENCE_PATH.findall(row.evidence)
        assert paths, f"{row.ident} cites no path"
        missing = [path for path in paths if not (ROOT / path).is_file()]
        assert not missing, f"{row.ident} cites missing files: {missing}"


def test_no_useless_or_inapplicable_row_is_written_as_passed() -> None:
    assert not [p for p in problems(document()) if p.startswith("passed:")]


def test_duplicate_and_git_findings_are_recorded() -> None:
    text = document()
    assert "2 条重复粘贴" in text
    assert "## 2. 本地未推送检查结论" in text
    assert "CONTRIBUTING.md" in text
    assert not [p for p in problems(text) if p.startswith("findings:")]


def test_absent_entities_have_no_runtime_entity() -> None:
    """「不适用」must stay a fact about the source tree, not a rhetorical device."""
    files = list(SRC.rglob("*.py"))
    assert len(files) > 100
    corpus = {
        path: path.read_text(encoding="utf-8", errors="replace") for path in files
    }
    for word in ABSENT_ENTITIES:
        hits = [
            str(path.relative_to(ROOT))
            for path, source in corpus.items()
            if re.search(re.escape(word), source, re.IGNORECASE)
        ]
        assert not hits, f"{word} unexpectedly has a runtime entity: {hits}"


def test_tampering_is_detected() -> None:
    text = document()
    assert not problems(text), "the committed document must be clean"

    wrong_bucket = text.replace(
        "| 没有用 | 本仓检索是 BM25", "| 已通过 | 本仓检索是 BM25", 1
    )
    assert any(p.startswith(("verdict:", "summary:")) for p in problems(wrong_bucket))

    invented = text.replace(
        "`src/soapbot/plugins/loader.py`", "`src/soapbot/plugins/gone.py`", 1
    )
    assert invented != text, "the probe must actually change the document"
    assert any(p.startswith("path:") for p in problems(invented))

    wrong_summary = text.replace("该落实 12、", "该落实 11、", 1)
    assert any(p.startswith("summary:") for p in problems(wrong_summary))

    without_a_row = "\n".join(
        line for line in text.splitlines() if not line.startswith("| 14 |")
    )
    assert any(p.startswith(("rows:", "summary:")) for p in problems(without_a_row))
