"""Accessibility checks that can be automated.

Only two things here are mechanically verifiable: contrast ratios and "no colour
escapes the token layer". Everything else WCAG asks for — reading order, focus
sequence, whether an aria-label actually describes the control — needs a person
with a screen reader, and pretending otherwise with a green checkmark would be
worse than leaving it to the checklist in `docs/architecture.md`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_contrast.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_contrast", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_contrast_script_exists() -> None:
    assert SCRIPT.is_file(), "对比度校验脚本缺失，make check 会静默放过调色板回归"


def test_all_palette_pairs_pass_wcag_aa() -> None:
    mod = _load_script()
    failures: list[str] = []
    failures += mod.check(mod.BASE_CSS, mod.REQUIRED_PAIRS)
    assert not failures, "对比度不达标：\n" + "\n".join(failures)


def test_board_palette_matches_console() -> None:
    """The board and the console share one palette.

    They are separate files because one is served by the app and the other opened
    from disk, but a divergence means "the board passes contrast and the console
    does not" — a difference nobody would notice until an audit.
    """
    mod = _load_script()
    base = mod.parse_tokens(mod.BASE_CSS)
    board = mod.parse_tokens(mod.BOARD_CSS)
    # Only colours have to agree. Type stacks and radii are allowed to differ — the
    # board is a standalone page and picks its own rhythm; a font token that has to
    # stay byte-identical across two files is a coupling nobody benefits from.
    def is_colour(value: str) -> bool:
        v = value.strip()
        return v.startswith("#") or v.startswith("rgb")

    shared = sorted(n for n in set(base) & set(board) if is_colour(base[n]) and is_colour(board[n]))
    assert "--brand" in shared, "两个文件的 token 命名已经分叉，共享色值无法比较"
    mismatched = {n: (base[n], board[n]) for n in shared if base[n].lower() != board[n].lower()}
    assert not mismatched, f"共享色彩 token 取值不一致：{mismatched}"


def test_no_hardcoded_colours_outside_root() -> None:
    mod = _load_script()
    failures = mod.check_no_hardcoded(mod.BASE_CSS) + mod.check_no_hardcoded(mod.BOARD_CSS)
    assert not failures, "存在绕过 token 的硬编码颜色：\n" + "\n".join(failures)


def test_script_exits_zero_as_a_process() -> None:
    """`make check` calls it as a subprocess; import-level success is not enough."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout + result.stderr
