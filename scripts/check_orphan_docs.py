#!/usr/bin/env python
"""Fail when a document in ``docs/`` is never referenced from anywhere.

The reverse of ``check_doc_links.py``: that gate proves every link *resolves*;
this one proves every document is *reachable*. Two real docs sat unlinked for
months (a 15-minute QQ quickstart, the persona auto-growth boundary) — both
passed every gate, because "the link works" and "anyone can find it" are
different properties.

A document counts as referenced when its basename appears anywhere else in the
repository's text (markdown, source, tests, scripts, workflows, webui sources).
A standalone archive is a legitimate decision, not an oversight — each entry in
``_STANDALONE`` below must carry a reason, and a stale allowlist entry (the
document it names no longer exists) fails the gate like an orphan would.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Documents that are deliberately standalone. Each entry is a decision with a
#: reason; when the reason expires (the doc gets linked, or the doc is deleted),
#: the entry must go too.
_STANDALONE: dict[str, str] = {
    # 批次评估档案：结论经 PR（#91）审阅合并，不参与日常文档网络。
    "reference-batch9-evaluation.md": "批次评估档案，经 PR 记录可追溯，不挂日常文档网络",
    # 两份审计存档：结论已由后续修复 PR 落地，档案按日期可追溯。
    "code-audit-2026-11.md": "代码层审计存档（2026-11-13），修复项经 #63 后各 PR 落地",
    "security-review-2026-11.md": "全库安全审查存档（2026-11-12），双视角复核记录",
}

#: 文本语料： basename 会在这里出现就算「被引用」。
_CORPUS_GLOBS = (
    ("", "*.md"),
    ("docs", "**/*.md"),
    ("src", "**/*.py"),
    ("tests", "*.py"),
    ("scripts", "*.py"),
    ("webui/src", "**/*.ts"),
    ("webui/src", "**/*.vue"),
    ("desktop", "**/*.rs"),
    ("mobile/lib", "**/*.dart"),
    (".github/workflows", "*.yml"),
)


def _corpus_text() -> dict[str, str]:
    """Every corpus file keyed by repo-relative posix path (its own text kept
    separate so a document's *own* mention of its name never counts)."""
    texts: dict[str, str] = {}
    for base, pattern in _CORPUS_GLOBS:
        base_dir = ROOT / base if base else ROOT
        for path in sorted(base_dir.glob(pattern)):
            try:
                texts[path.relative_to(ROOT).as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
    return texts


def find_orphans(doc_paths: list[str], texts: dict[str, str]) -> list[str]:
    """Pure helper so tests can pin the detection without the real repo.

    A document is an orphan when its basename appears in NO other file — its
    own content does not count, otherwise a doc that never mentions itself
    would read as referenced by exactly one (nonexistent) source.
    """
    orphans: list[str] = []
    for path in doc_paths:
        name = Path(path).name
        others = "\n".join(text for rel, text in texts.items() if rel != path)
        if name not in others:
            orphans.append(name)
    return sorted(orphans)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    docs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("**/*.md"))
    basenames = [Path(d).name for d in docs]
    texts = _corpus_text()

    stale = sorted(name for name in _STANDALONE if name not in basenames)
    if stale:
        print("allowlist 指向不存在的文档（过期条目要删掉）：")
        for name in stale:
            print(f"  - {name}")
        return 1

    orphans = [Path(d).name for d in find_orphans(docs, texts) if Path(d).name not in _STANDALONE]
    total = len(docs)
    if orphans:
        print(f"docs 共 {total} 个，其中 {len(orphans)} 个从未被引用（孤儿文档）：")
        for name in orphans:
            reason = _STANDALONE.get(name)
            print(f"  - {name}" + (f"（standalone：{reason}）" if reason else ""))
        print("修法二选一：从相关文档/README 挂链，或在 _STANDALONE 里声明 standalone 与理由。")
        return 1
    print(f"orphan docs ok: {total} 个文档全部可达或显式 standalone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
