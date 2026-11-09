"""Per-file test counts quoted in the docs must equal the real collected count.

Why this exists
---------------
The docs tell a reader *how much* stands behind a claim. Nine ``（N 项）`` numbers were
wrong when this module was written, and six had survived several rounds — because
``scripts/check_test_gaps.py`` only pins the *total* "N passed" in a few live documents
and never looks at a per-file claim. A later round found the same blind spot in command
comments: ``docs/plugin-security-review.md`` still said ``# 75 passed`` for a file that
collects 74, even after the prose next to it had been corrected.

Two shapes of claim
-------------------
1. ``tests/xxx.py``（N 项）— prose stating how many cases stand behind a capability.
2. A pytest command that names specific test files and ends in ``# N passed``, or has
   that comment on the following line. This claims what *that command* prints today.
   PowerShell backtick continuations are joined first: two documents spread one command
   over three lines with the comment on the last one.

A command that runs ``tests/`` as a whole is a round report, not a per-file claim; its
number belongs to the progress board and is pinned by ``scripts/check_test_gaps.py``.

How the truth is obtained
-------------------------
``pytest --collect-only -q`` in a subprocess, once for every file any document names.
Collection does not execute tests, so it needs no database, no network and no persona
configuration — it is deterministic. Counting ``passed`` instead would fold skips and
random failures into the baseline, which is a gate built on sand.

One subprocess, not one per file: 27 files at ~0.5 s of interpreter start each would add
half a minute to ``make check`` for no extra information. Every test in this module asks
for the same name set so the memoised collector runs once.

What is deliberately *not* checked
----------------------------------
A round report ("那一轮 435 passed") is a record of a day. Pinning it to today's count
would forbid writing history.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: `tests/<name>.py`（N 项）— the backtick around the path is optional because a few
#: lines wrap the path in one and a few do not.
#:
#: Deliberately anchored on the path *before* the number: the reverse order
#: ("74 项（`tests/...`）") is not used anywhere in this repo, and accepting both would
#: mean the regex also matches prose like "20 项边界（见 `tests/...`）".
CLAIM = re.compile(r"tests/([A-Za-z0-9_*]+\.py)`?\s*[（(]\s*(\d+)\s*项")

#: A file named by a pytest command. Requiring the ``.py`` suffix is what keeps a whole
#: `-m pytest tests/ -q` invocation out of this gate: that one reports a round's total.
COMMAND_FILE = re.compile(r"tests/([A-Za-z0-9_*]+\.py)")
#: Both inline (`... -q   # 74 passed`) and standalone (`# 128 passed`) spellings occur.
COMMAND_PASSED = re.compile(r"#\s*(\d+)\s+passed\b")

#: Claims that name a *subset* of a file on purpose, with the reason each one is not the
#: file total. Kept as data so the reason travels with the exemption, and so adding one
#: means editing this table rather than loosening the regex for everybody.
#:
#: Loosening the regex instead was the tempting option and the wrong one: it would make
#: the "file total" assertion silently stop applying to exactly the two files where a
#: reader is most likely to be misled by a number that looks like a total.
SUBSET_CLAIMS: dict[tuple[str, int], str] = {
    ("test_mcp_write.py", 3): (
        "列举的是 `McpManager.reload` 热生效的三条断言（保留未变 client、改名才重启、"
        "空列表），文件本身 18 项覆盖增删改与 argv 强制"
    ),
    ("test_posture.py", 7): (
        "列举的是上游连通性规则的七种输入（空配置、缺文件、坏 YAML、本机端点、明文 http、"
        "远端、进报告），文件本身 51 项"
    ),
}

#: A regex that silently stops matching would report "0 claims, 0 failures" — green for
#: the worst possible reason. The real count is 24; the floor is set below it so that
#: adding a document does not require touching this file, but a broken regex fails.
MINIMUM_CLAIMS = 20

#: Four commands name specific files today. Same purpose as MINIMUM_CLAIMS: if the parser
#: stops matching, "0 command claims, 0 failures" must not look like a green gate.
MINIMUM_COMMAND_CLAIMS = 3

#: Collection imports every test module, including the slow ones; 300 s is far above the
#: observed ~15 s and still short enough that a hang is reported rather than waited on.
COLLECT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Claim:
    source: str
    lineno: int
    name: str
    count: int

    def where(self) -> str:
        return f"{self.source}:{self.lineno}"

    def is_subset(self) -> bool:
        return (self.name, self.count) in SUBSET_CLAIMS


@dataclass(frozen=True)
class CommandClaim:
    source: str
    lineno: int
    files: tuple[str, ...]
    count: int

    def where(self) -> str:
        return f"{self.source}:{self.lineno}"


def documents() -> list[Path]:
    """Every document that a reader could take as the current state."""
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def extract_claims(text: str, source: str = "<memory>") -> list[Claim]:
    """All `tests/<name>.py`（N 项）claims in ``text``, in file order."""
    claims: list[Claim] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in CLAIM.finditer(line):
            claims.append(Claim(source, lineno, match.group(1), int(match.group(2))))
    return claims


def extract_command_claims(text: str, source: str = "<memory>") -> list[CommandClaim]:
    """Commands naming test files whose ``# N passed`` comment can be checked.

    Two spellings occur in this repo and both are handled:

    * inline — ``... -m pytest tests/x.py -q   # 74 passed``
    * standalone — a multi-line command ending in ``-q``, then ``# 128 passed`` on the
      next line. PowerShell backtick continuations are joined into one logical command
      first, otherwise only the last fragment (which names no file) would be seen.

    A command whose only test argument is the ``tests/`` directory is deliberately not
    returned: it reports a round's total, which the progress board owns.
    """
    lines = text.splitlines()
    claims: list[CommandClaim] = []
    index = 0
    while index < len(lines):
        logical = lines[index]
        while logical.rstrip().endswith("`") and index + 1 < len(lines):
            logical = logical.rstrip()[:-1] + " " + lines[index + 1].strip()
            index += 1

        found = COMMAND_FILE.findall(logical)
        if "pytest" in logical and found:
            files = tuple(dict.fromkeys(found))
            match = COMMAND_PASSED.search(logical)
            comment_lineno = index + 1
            if match is None and index + 1 < len(lines):
                following = lines[index + 1].strip()
                standalone = re.fullmatch(r"#\s*(\d+)\s+passed\b.*", following)
                if standalone:
                    match = standalone
                    comment_lineno = index + 2
            if match is not None:
                claims.append(
                    CommandClaim(source, comment_lineno, files, int(match.group(1)))
                )
        index += 1
    return claims


def claimed_files() -> list[str]:
    """Distinct file/glob names any document names, sorted for a stable command line."""
    names: set[str] = set()
    for path in documents():
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            names.update(claim.name for claim in extract_claims(text))
            for command in extract_command_claims(text):
                names.update(command.files)
    return sorted(names)


@lru_cache(maxsize=1)
def all_claimed_names() -> tuple[str, ...]:
    """One stable name set, so every test shares a single collector subprocess."""
    return tuple(claimed_files())


def expand(name: str) -> list[Path]:
    """Resolve one claim name to the files it covers.

    A glob is resolved here rather than handed to pytest: pytest's own argument globbing
    treats ``tests/test_security_*.py`` as a literal path and collects nothing (verified),
    which would make every glob claim compare against zero.
    """
    if "*" in name:
        return sorted(TESTS.glob(name))
    path = TESTS / name
    return [path] if path.is_file() else []


def collect_counts(names: list[str]) -> dict[str, int]:
    """Real collected case counts, keyed by the claim name (globs summed).

    Raises ``AssertionError`` rather than skipping when collection fails: a gate that
    turns itself off when it cannot measure is indistinguishable from a passing one.
    """
    return _collect_counts_cached(tuple(names))


@lru_cache(maxsize=4)
def _collect_counts_cached(names: tuple[str, ...]) -> dict[str, int]:
    """Memoised so the two tests that need the truth pay for one subprocess, not two."""
    files: list[Path] = []
    for name in names:
        files.extend(expand(name))
    if not files:
        raise AssertionError("no test file could be resolved from the documents' claims")

    env = dict(os.environ)
    # The suite is normally run from the repo root with the package installed, but a
    # contributor running a single file from elsewhere should still get a measurement
    # instead of a collection error.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *map(str, files)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=COLLECT_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode not in (0, 5):  # 5 == "no tests collected"
        raise AssertionError(
            "pytest --collect-only failed, so the documented counts cannot be verified:\n"
            f"{output[-4000:]}"
        )

    per_file: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        if "::" in line:
            # Normalised to forward slashes: pytest echoes the path it was given, and on
            # Windows that can come back as `tests\test_x.py`. Without this, every claim
            # would compare against 0 and the gate would fail for the wrong reason.
            relative = line.split("::", 1)[0].strip().replace("\\", "/")
            per_file[relative] = per_file.get(relative, 0) + 1

    # Cross-check the node-id count against pytest's own summary. A mismatch means the
    # output format changed and the per-file split above is no longer trustworthy.
    summary = re.search(r"(\d+) tests? collected", completed.stdout)
    if summary and int(summary.group(1)) != sum(per_file.values()):
        raise AssertionError(
            "pytest reported "
            f"{summary.group(1)} collected but {sum(per_file.values())} node ids were "
            "parsed; the output format changed and this gate needs updating"
        )

    counts: dict[str, int] = {}
    for name in names:
        resolved = expand(name)
        if not resolved:
            counts[name] = -1  # reported as "no such file" by compare()
            continue
        counts[name] = sum(
            per_file.get(path.relative_to(ROOT).as_posix(), 0) for path in resolved
        )
    return counts


def compare(claims: list[Claim], actual: dict[str, int]) -> list[str]:
    """One message per claim that disagrees with ``actual``."""
    problems: list[str] = []
    for claim in claims:
        if claim.is_subset():
            continue
        real = actual.get(claim.name)
        if real is None:
            # Only reachable when a caller passes a partial mapping; the gate itself
            # always measures every claimed name. Reported rather than skipped, because
            # silently treating "not measured" as "correct" is the failure mode this
            # whole module exists to prevent.
            problems.append(f"{claim.where()} 提到 {claim.name}，但没有为它取到真实项数")
        elif real < 0:
            problems.append(f"{claim.where()} 写着 {claim.name}，但 tests/ 下没有这个文件")
        elif real != claim.count:
            problems.append(
                f"{claim.where()} 写着 {claim.name}（{claim.count} 项），"
                f"实际收集到 {real} 项"
            )
    return problems


def compare_command_claims(
    claims: list[CommandClaim], actual: dict[str, int]
) -> list[str]:
    """One message per command whose comment disagrees with its named files."""
    problems: list[str] = []
    for claim in claims:
        missing = [name for name in claim.files if actual.get(name, -1) < 0]
        if missing:
            problems.append(f"{claim.where()} 的命令列出不存在的文件：{missing}")
            continue
        total = sum(actual[name] for name in claim.files)
        if total != claim.count:
            problems.append(
                f"{claim.where()} 写着 # {claim.count} passed，但列出的 "
                f"{len(claim.files)} 个文件实际共 {total} 项"
            )
    return problems


def test_every_documented_count_matches_the_collected_count() -> None:
    """The gate itself."""
    claims: list[Claim] = []
    for path in documents():
        if not path.is_file():
            continue
        claims.extend(
            extract_claims(
                path.read_text(encoding="utf-8", errors="replace"),
                path.relative_to(ROOT).as_posix(),
            )
        )

    assert len(claims) >= MINIMUM_CLAIMS, (
        f"只抽到 {len(claims)} 条「tests/xxx.py（N 项）」声明，低于下界 "
        f"{MINIMUM_CLAIMS}；正则很可能已经失配，这条断言正在空转"
    )

    problems = compare(claims, collect_counts(list(all_claimed_names())))
    assert not problems, "文档里的用例数与真实收集数不一致：\n" + "\n".join(problems)


def test_command_comments_match_the_files_they_name() -> None:
    """The gate for shape 2: a command's `# N passed` must equal its named files."""
    claims: list[CommandClaim] = []
    for path in documents():
        if not path.is_file():
            continue
        claims.extend(
            extract_command_claims(
                path.read_text(encoding="utf-8", errors="replace"),
                path.relative_to(ROOT).as_posix(),
            )
        )

    assert len(claims) >= MINIMUM_COMMAND_CLAIMS, (
        f"只抽到 {len(claims)} 条带 # N passed 的单文件命令，低于下界 "
        f"{MINIMUM_COMMAND_CLAIMS}；解析器很可能已经失配，这条断言正在空转"
    )
    problems = compare_command_claims(claims, collect_counts(list(all_claimed_names())))
    assert not problems, "文档命令注释里的用例数与真实收集数不一致：\n" + "\n".join(
        problems
    )


def test_the_command_gate_would_catch_a_wrong_number() -> None:
    """Reverse case for the command gate, with a synthesised claim."""
    claims = extract_command_claims(
        "python -m pytest tests/test_example.py -q   # 4 passed\n", "fake.md"
    )
    assert len(claims) == 1
    assert claims[0].files == ("test_example.py",)

    problems = compare_command_claims(claims, {"test_example.py": 5})
    assert len(problems) == 1
    assert "fake.md:1" in problems[0] and "4 passed" in problems[0]
    assert compare_command_claims(claims, {"test_example.py": 4}) == []


def test_powershell_continuations_are_joined_before_counting() -> None:
    """A three-line command with a standalone comment must be one claim, not three."""
    text = "python -m pytest tests/a.py `\n    tests/b.py -q\n# 7 passed\n"
    claims = extract_command_claims(text, "fake.md")
    assert len(claims) == 1
    assert claims[0].files == ("a.py", "b.py")
    assert claims[0].lineno == 3
    assert compare_command_claims(claims, {"a.py": 4, "b.py": 3}) == []
    assert len(compare_command_claims(claims, {"a.py": 4, "b.py": 4})) == 1


def test_full_suite_commands_are_round_reports_not_claims() -> None:
    """`-m pytest tests/ -q` reports a round; the progress board owns its number."""
    assert (
        extract_command_claims(
            "python -m pytest tests/ -q   # 405 passed, 1 skipped\n", "fake.md"
        )
        == []
    )


def test_the_comparison_would_catch_a_wrong_number() -> None:
    """Reverse case: prove the assertion above is not vacuous.

    A gate that passes because it compared nothing is worse than no gate. Here the claim
    is synthesised, so the test cannot be satisfied by the documents happening to be
    correct today.
    """
    claims = extract_claims("验证见 `tests/test_example.py`（4 项）。", "fake.md")
    assert len(claims) == 1, "the regex no longer matches the shape it exists to check"

    problems = compare(claims, {"test_example.py": 5})
    assert len(problems) == 1
    assert "fake.md:1" in problems[0]
    assert "4 项" in problems[0] and "5 项" in problems[0]

    assert compare(claims, {"test_example.py": 4}) == []


def test_a_glob_claim_is_the_sum_of_its_files() -> None:
    """`test_security_*.py`（N 项）means the sum, not the first match."""
    claims = extract_claims("见 `tests/test_glob_*.py`（7 项）。", "fake.md")
    assert claims[0].name == "test_glob_*.py"

    # Two files of 4 and 3 must satisfy a claim of 7; a claim of 4 must not.
    assert compare(claims, {"test_glob_*.py": 7}) == []
    assert len(compare(claims, {"test_glob_*.py": 4})) == 1


def test_a_missing_file_is_reported_rather_than_counted_as_zero() -> None:
    """A renamed test file must fail loudly, not silently compare against 0."""
    claims = extract_claims("见 `tests/test_gone.py`（3 项）。", "fake.md")
    problems = compare(claims, {"test_gone.py": -1})
    assert len(problems) == 1
    assert "没有这个文件" in problems[0]


def test_every_subset_exception_is_still_real() -> None:
    """A stale exemption hides a claim that could be checked in full.

    Fails when an allowlisted claim no longer appears in any document, or when it has
    grown to equal the file total — at which point it is not a subset any more and the
    exemption is only hiding the check.
    """
    documented = {
        (claim.name, claim.count)
        for path in documents()
        if path.is_file()
        for claim in extract_claims(path.read_text(encoding="utf-8", errors="replace"))
    }
    stale = sorted(set(SUBSET_CLAIMS) - documented)
    assert not stale, f"SUBSET_CLAIMS 里的条目在文档中已不存在：{stale}"

    totals = collect_counts(list(all_claimed_names()))
    for (name, count), reason in SUBSET_CLAIMS.items():
        assert totals[name] > count, (
            f"{name} 的子集声明（{count} 项）已不小于文件总数（{totals[name]} 项），"
            f"这条豁免应当删除：{reason}"
        )
