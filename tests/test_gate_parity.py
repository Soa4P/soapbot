"""`make check` and the CI `backend` job must run the same gates.

The defect this pins down was measured, not imagined: three static gates
(`check_deps.py`, `check_console_encoding.py`, `check_deploy.py`) ran only in CI. All
three are offline, deterministic and finish in about a second, so they were exactly the
gates that belonged on the developer's machine — and their absence meant a contributor
could get a green `make check` and a red `backend` job on the same commit.

That is the failure mode the `Makefile` header promises cannot happen:

    Every target here is also what CI runs, so "works on my machine" and "passes in
    CI" are the same command rather than two similar ones.

A promise in a comment is not a gate. This module turns it into one: it reads both
files, resolves which scripts each side actually executes, and fails when the sets
differ by anything other than the two exceptions named below.

Why parse instead of hard-coding two lists: a hard-coded list passes forever after
someone adds a gate to `ci.yml` and forgets the `Makefile`. Parsing the recipes means a
newly added target is picked up automatically, and the diff is computed from what the
files really say.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: Gates CI runs that `make check` cannot, with the reason each one is excluded.
#:
#: Kept as data rather than a comment so the reason travels with the assertion: a
#: future reader who wants to add one of these to `make check` has to delete an entry
#: here, which is the moment to reconsider whether it is really runnable locally.
CI_ONLY = {
    "check_secrets.py": (
        "needs the git history of the commit under review; locally it would scan "
        "whatever happens to be staged"
    ),
    "pip-audit": "needs the network; a gate that fails when PyPI is slow gets re-run until green",
    "check_pr_title.py": (
        "checks the title of a pull request; `make check` runs on a working tree and has "
        "no title to inspect, and on a direct push there is no PR either"
    ),
}

_SCRIPT = re.compile(r"scripts/(check_[a-z0-9_]+\.py)")
_TARGET_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:(?!=)\s*(.*)$")
_CHECK_LINE = re.compile(r"^check\s*:\s*(.+)$", re.MULTILINE)


def _makefile_targets(text: str) -> dict[str, str]:
    """Map target name to its recipe body (tab-indented lines following the header).

    Only single-line prerequisite lists are supported, which is what this `Makefile`
    uses; a backslash continuation would silently truncate, so it is rejected rather
    than mis-parsed.
    """
    targets: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("\t"):
            if current is not None:
                targets[current] += line + "\n"
            continue
        match = _TARGET_LINE.match(line)
        if match:
            current = match.group(1)
            if line.rstrip().endswith("\\"):
                raise AssertionError(
                    f"Makefile target {current!r} uses a line continuation; "
                    "extend _makefile_targets before relying on it"
                )
            targets[current] = ""
        elif line.strip() and not line.lstrip().startswith("#"):
            current = None
    return targets


def makefile_gates(text: str | None = None) -> set[str]:
    """Scripts (and the two non-script gates) that `make check` executes."""
    source = MAKEFILE.read_text(encoding="utf-8") if text is None else text
    match = _CHECK_LINE.search(source)
    assert match, "the `check:` target disappeared from the Makefile"

    prerequisites = match.group(1).split()
    recipes = _makefile_targets(source)

    gates: set[str] = set()
    for name in prerequisites:
        body = recipes.get(name)
        assert body is not None, f"`check` depends on {name!r}, which has no recipe"
        found = _SCRIPT.findall(body)
        if found:
            gates.update(found)
        elif "ruff" in body:
            gates.add("ruff")
        elif "pytest" in body:
            gates.add("pytest")
        else:
            raise AssertionError(
                f"`check` prerequisite {name!r} runs neither a scripts/check_*.py "
                f"gate nor ruff/pytest; teach this test what it is:\n{body}"
            )
    return gates


def ci_gates(text: str | None = None) -> set[str]:
    """Gates the CI `backend` job executes, comments excluded.

    Comments matter here: several of them name a script to explain why it is *not*
    run, and counting those would make the two sides agree for the wrong reason.
    """
    source = CI.read_text(encoding="utf-8") if text is None else text
    backend = source.split("  backend:", 1)[1].split("\n  types:", 1)[0]

    live = "\n".join(
        line for line in backend.splitlines() if not line.lstrip().startswith("#")
    )
    gates = set(_SCRIPT.findall(live))
    if re.search(r"python -m ruff\b", live):
        gates.add("ruff")
    if re.search(r"python -m pytest\b", live):
        gates.add("pytest")
    if "pip_audit" in live or "pip-audit" in live:
        gates.add("pip-audit")
    return gates


def test_make_check_runs_every_locally_runnable_ci_gate() -> None:
    """The only gates in CI but not in `make check` are the documented exceptions."""
    missing = ci_gates() - makefile_gates() - set(CI_ONLY)
    assert not missing, (
        "these gates run in CI but not in `make check`, so a contributor can get a "
        f"green local run and a red backend job: {sorted(missing)}"
    )


def test_make_check_adds_no_gate_ci_does_not_run() -> None:
    """The reverse direction: a local-only gate makes `make check` slower than CI.

    Not a correctness bug on its own, but it breaks the "same command" claim in the
    other direction, and the usual cause is a gate that was added locally and never
    wired into CI — which then never protects anyone but the author.
    """
    extra = makefile_gates() - ci_gates()
    assert not extra, (
        "these gates run in `make check` but not in CI, so they protect nothing on a "
        f"pull request: {sorted(extra)}"
    )


def test_the_two_exceptions_are_still_real() -> None:
    """A stale exception hides a gate that could be local.

    If `check_secrets.py` ever grows a mode that works without git history, or
    `pip-audit` becomes a vendored offline scan, the entry above should go away. This
    fails when an exception names something neither side runs any more.
    """
    both = ci_gates() | makefile_gates()
    stale = set(CI_ONLY) - both
    assert not stale, f"CI_ONLY lists gates that no longer exist anywhere: {sorted(stale)}"


def test_the_parity_check_would_catch_a_regression() -> None:
    """Reverse case: prove the assertion above is not vacuous.

    A parity test that passes because both parsers return the same empty set is worse
    than no test — it reports agreement it never verified. Dropping one gate from the
    `check` line must make the forward assertion fail.
    """
    source = MAKEFILE.read_text(encoding="utf-8")
    broken = re.sub(r"^check:\s*(.+)$", lambda m: "check: " + m.group(1).replace("console-encoding", ""), source, count=1, flags=re.MULTILINE)
    assert broken != source, "could not remove console-encoding from the check line"

    missing = ci_gates() - makefile_gates(broken) - set(CI_ONLY)
    assert missing == {"check_console_encoding.py"}, (
        "removing a gate from `check` did not show up as a parity failure; the test "
        f"is not measuring what it claims (got {sorted(missing)})"
    )


def test_every_gate_script_is_covered_by_one_side_or_the_other() -> None:
    """A `scripts/check_*.py` nobody runs is dead weight that looks like a gate."""
    on_disk = {path.name for path in (ROOT / "scripts").glob("check_*.py")}
    wired = ci_gates() | makefile_gates()
    orphans = on_disk - wired
    assert not orphans, (
        "these check scripts exist but neither `make check` nor CI runs them, so they "
        f"are not gates: {sorted(orphans)}"
    )


def test_the_documented_exceptions_are_actually_documented() -> None:
    """The exclusion is only honest if the reader is told about it.

    A reader who runs `make check`, sees green, and pushes is relying on the claim in
    the README. If the two exceptions live only in this test file, the claim is true
    for the maintainer and false for everyone else. So the README has to name both
    reasons, in the section that makes the claim.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    gates_section = readme.split("## 门禁", 1)
    assert len(gates_section) == 2, "the README no longer has a 门禁 section"
    body = gates_section[1].split("\n## ", 1)[0]

    for gate in CI_ONLY:
        assert gate in body, (
            f"README 的门禁一节没有提到 {gate}，读者会以为 `make check` 覆盖了它"
        )
    # The reasons, not just the names: a bare list of exclusions invites someone to
    # "fix" it by adding a gate that cannot work offline.
    assert "git 历史" in body, "README 没说 check_secrets 为什么不能在本地跑"
    assert "联网" in body or "网络" in body, "README 没说 pip-audit 为什么不能在本地跑"


def test_the_boundary_audit_needle_still_matches_the_makefile() -> None:
    """`check_security_boundaries.py` greps the Makefile help text for a literal.

    That coupling is invisible from the Makefile side: rewording the help line reads
    like a copy edit and silently turns `make boundary-audit` red. This test makes the
    coupling visible at the place where the edit happens, with a message that names the
    literal instead of leaving someone to decode a boundary failure.
    """
    needle = "20 项安全与错误日志边界审计"
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert needle in makefile, (
        f"Makefile 的 help 文案里没有 {needle!r}，"
        "scripts/check_security_boundaries.py 的 COUNT_CLAIMS 会因此判定失败；"
        "改文案时请保留这个子串"
    )
