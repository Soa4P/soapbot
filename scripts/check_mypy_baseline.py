"""Keep the type-error count from growing.

Why this exists
---------------
``mypy`` has run in CI for a while with ``continue-on-error: true``. That makes 79
errors visible in a log nobody opens and lets the 80th in without a word — the same
defect that made ``pip-audit`` blocking: a check that cannot fail is not a gate.

A total is the right granularity. A per-file baseline is more precise and turns every
refactor that moves a function into a failure, which trains people to raise the number
instead of reading it. One number answers one question: is the debt growing?

This guard does not ask anyone to fix the 79. Fixing them is a separate, deliberate job
— most are ``Any`` leaking from third-party stubs plus a handful of real signature
mismatches. It only refuses new ones.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(__file__).with_name("mypy_baseline.txt")
SUMMARY = re.compile(r"Found (\d+) errors? in (\d+) files?")


def read_baseline() -> int:
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return int(stripped)
    raise SystemExit(f"{BASELINE.name} has no number in it")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    baseline = read_baseline()
    completed = subprocess.run(
        [sys.executable, "-m", "mypy", "src"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout + completed.stderr

    if completed.returncode == 2 and "No module named mypy" in output:
        print('mypy is not installed; run `pip install -e ".[dev]"`', file=sys.stderr)
        return 2

    match = SUMMARY.search(output)
    if match is None:
        # A crash, a bad config or a mypy that changed its summary line. Reporting zero
        # here would turn the guard into a check that always passes.
        print("mypy produced no summary; refusing to guess:", file=sys.stderr)
        print("\n".join(output.splitlines()[-12:]), file=sys.stderr)
        return 2

    errors = int(match.group(1))
    files = int(match.group(2))

    if errors > baseline:
        print(
            f"type errors grew to {errors}, above the {baseline} baseline "
            f"({files} files). Full output:",
            file=sys.stderr,
        )
        print("\n".join(output.splitlines()[-25:]), file=sys.stderr)
        return 1

    if errors < baseline:
        # Deliberately not "lower the number now": the baseline is the larger of two
        # environments (see the file), so a local run is expected to sit one below it.
        # Telling people to lower it would turn CI red for a difference that has nothing
        # to do with their change.
        print(f"type errors: {errors}, under the {baseline} baseline ({files} files)")
    else:
        print(f"type errors unchanged at {errors} ({files} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
