"""The optional writing-style scan and the external-reference deliverables."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_flavor_scan import EXEMPT_FILES, PATTERNS, main, scan  # noqa: E402


def _tmp(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sample.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_each_pattern_is_a_real_signal(tmp_path: Path) -> None:
    samples = {
        "空洞升华": "这标志着一个关键的里程碑。",
        "模糊归因": "专家表示情况正在好转。",
        "整齐收尾": "总之，问题已经解决。",
    }
    for label, text in samples.items():
        hits = scan([_tmp(tmp_path, text)])
        assert any(f"[{label}]" in hit for hit in hits), label


def test_a_single_contrast_is_not_a_signal_but_a_tic_is(tmp_path: Path) -> None:
    one = "不是速度不够，而是路径不对。"
    assert scan([_tmp(tmp_path, text=one)]) == []
    three = "\n".join(
        [
            "不是速度不够，而是路径不对。",
            "不是人手不足，而是分工不清。",
            "不是预算太少，而是顺序错了。",
        ]
    )
    assert any("[假对比三连]" in hit for hit in scan([_tmp(tmp_path, three)]))


def test_the_scan_is_read_only_and_repeatable(tmp_path: Path) -> None:
    path = _tmp(tmp_path, "众所周知，这是一次赋能。")
    before = path.read_text(encoding="utf-8")
    first = scan([path])
    second = scan([path])
    assert first == second
    assert path.read_text(encoding="utf-8") == before


def test_strict_mode_is_the_only_mode_that_fails(capsys) -> None:
    original = scan

    import scripts.ai_flavor_scan as module

    module.scan = lambda paths=None: ["sample.md:1 [空洞升华] 赋能"]  # type: ignore[assignment]
    try:
        assert main([]) == 0
        assert main(["--strict"]) == 1
    finally:
        module.scan = original  # type: ignore[assignment]
    assert "赋能" in capsys.readouterr().out


def test_historical_quote_files_are_exempt() -> None:
    assert "reference-external-2026-11.md" in EXEMPT_FILES
    assert "writing-style.md" in EXEMPT_FILES
    assert set(PATTERNS) == {"空洞升华", "模糊归因", "整齐收尾", "假对比三连"}


def test_the_external_analysis_records_all_three_link_outcomes() -> None:
    text = (ROOT / "docs/reference-external-2026-11.md").read_text(encoding="utf-8")
    assert "zuiho-kai/bothouse" in text
    assert "mearihaka/dsh-longing" in text
    assert "Fangi8" in text and "待用户提供正确地址" in text
    assert "不引入" in text or "没有引入" in text


def test_the_adapted_plugin_only_declares_read_capabilities() -> None:
    manifest = (
        ROOT / "src/soapbot/examples/plugins/warmth-observer/plugin.yaml"
    ).read_text(encoding="utf-8")
    assert "  - command" in manifest
    assert "  - session" in manifest
    for forbidden in ("  - send", "  - cron", "  - storage", "  - http"):
        assert forbidden not in manifest
    assert (
        ROOT / "src/soapbot/examples/plugins/warmth-observer/main.py"
    ).is_file()
