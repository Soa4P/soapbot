"""Optional, read-only scan for four kinds of filler in this repository's prose.

Adapted from the *constraints* of public "去 AI 味" skills, not from their output
templates (see docs/writing-style.md and docs/reference-external-2026-11.md §3):

* no author-identification: a hit is an editing signal, never a verdict;
* no silent rewriting: this script never modifies a file;
* no invented facts: it reports the line it found, nothing else.

It is deliberately not a CI gate. A check that can be quieted by deleting a word
trains people to delete words; a human decides whether a hit is really filler.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]

PATTERNS = {
    "空洞升华": re.compile(
        r"标志着.{0,12}里程碑|具有重要意义|赋能|闭环|底层逻辑|降维打击|开启新篇章"
    ),
    "模糊归因": re.compile(r"专家表示|研究表明|业内人士分析|众所周知|有专家指出"),
    "整齐收尾": re.compile(r"^(?:总之|综上所述|总而言之|由此可见)[，,：:]"),
    "假对比三连": re.compile(r"不是.{0,24}而是"),
}

#: A single "不是 X，而是 Y" is ordinary Chinese. Only a repeated tic is a signal;
#: judging one occurrence is exactly the author-identification mistake the skill
#: refuses to make.
CONTRAST_MIN = 3

#: Historical records and gate descriptions legitimately quote these words.
EXEMPT_FILES = {"reference-external-2026-11.md", "writing-style.md"}


def scan(paths: list[Path] | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths or TARGETS:
        if path.name in EXEMPT_FILES:
            continue
        try:
            shown = str(path.relative_to(ROOT))
        except ValueError:  # a caller outside the repo (tests, ad-hoc files)
            shown = path.name
        lines = path.read_text(encoding="utf-8").splitlines()
        contrasts: list[int] = []
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            for label, pattern in PATTERNS.items():
                if label == "假对比三连":
                    if pattern.search(stripped):
                        contrasts.append(number)
                    continue
                if pattern.search(stripped):
                    findings.append(f"{shown}:{number} [{label}] {stripped[:100]}")
        if len(contrasts) >= CONTRAST_MIN:
            findings.append(
                f"{shown} [假对比三连] {len(contrasts)} 处，行 {contrasts[:6]}"
            )
    return findings


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    findings = scan()
    if not findings:
        print("去 AI 味扫描：无命中")
        return 0
    print(f"去 AI 味扫描：{len(findings)} 处待人工判断")
    for finding in findings[:40]:
        print("  " + finding)
    if len(findings) > 40:
        print(f"  ... 另有 {len(findings) - 40} 处")
    return 1 if "--strict" in argv else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
