"""The orphan-docs gate: a document nobody references is a document nobody finds.

The reverse of ``check_doc_links.py`` — that gate proves links resolve, this one
proves documents are reachable. Pins the detection logic on synthetic corpora,
the stale-allowlist fail-closed behaviour, and one contract run against the real
repository.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_orphan_docs.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_orphan_docs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_find_orphans_reports_never_referenced_basenames() -> None:
    module = _module()
    texts = {
        "docs/linked.md": "从这里 [x](linked.md) 被别的文档引用",
        "docs/lonely.md": "只在它自己文件里出现——没有别人写它",
        "README.md": "提到 linked.md 多次没问题",
    }
    # lonely.md 的 basename 在「除它自己之外」的任何文件里都没出现 → 孤儿
    assert module.find_orphans(
        ["docs/linked.md", "docs/lonely.md"], texts
    ) == ["lonely.md"]


def test_own_mention_does_not_count_as_a_reference() -> None:
    """一个文档在自己的正文里写自己的文件名，不算被引用——否则自指即自证。"""
    module = _module()
    texts = {
        "docs/self.md": "self.md 是本文件的文件名，正文里提一次",
        "README.md": "与 docs 无关的根文档",
    }
    assert module.find_orphans(["docs/self.md"], texts) == ["self.md"]


def test_a_basename_mentioned_elsewhere_counts_as_referenced() -> None:
    module = _module()
    texts = {
        "docs/a.md": "a 的正文",
        "docs/b.md": "b 的正文",
        "README.md": "b.md 在根文档里被点名",
    }
    assert module.find_orphans(["docs/a.md", "docs/b.md"], texts) == ["a.md"]


def test_stale_allowlist_entry_fails_closed(tmp_path: Path, capsys) -> None:
    """allowlist 指向已删除的文档 = 过期决策，必须显式清理而不是静默跳过。"""
    module = _module()
    module._STANDALONE = {"gone.md": "理由已过期"}
    module.ROOT = tmp_path
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "linked.md").write_text("# x\n", encoding="utf-8")
    assert module.main() == 1
    assert "过期条目" in capsys.readouterr().out


def test_standalone_doc_does_not_fail_the_gate(tmp_path: Path, capsys) -> None:
    module = _module()
    module._STANDALONE = {"archive.md": "档案，经 PR 可追溯"}
    module.ROOT = tmp_path
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "archive.md").write_text("# 档案\n", encoding="utf-8")
    (tmp_path / "docs" / "linked.md").write_text("# 一个正常文档\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("见 docs/linked.md\n", encoding="utf-8")
    assert module.main() == 0
    assert "全部可达" in capsys.readouterr().out


def test_the_real_repository_has_no_unlisted_orphans() -> None:
    """Contract run: the live repo must stay clean under this gate."""
    module = _module()
    assert module.main() == 0
