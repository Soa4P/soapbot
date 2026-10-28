"""WCAG contrast check for the console palette.

Why a token-level script instead of axe-core: axe measures the rendered DOM and
therefore needs a browser in CI. This project has no frontend test runner and is
not about to grow one for a colour assertion. Parsing the `:root` block costs
milliseconds, runs inside `make check`, and catches the specific regression that
actually happens here — someone edits a token and nothing verifies the ratio.

What it cannot catch: a colour applied to the wrong element, or a hardcoded hex by
somebody who bypassed the tokens. That is why `base.css` has no hardcoded colours
below the `:root` block and this script asserts that too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_CSS = ROOT / "webui" / "src" / "styles" / "base.css"
BOARD_CSS = ROOT / "docs" / "progress" / "board.css"

# (foreground, background, minimum ratio, why)
TEXT = 4.5
UI = 3.0

REQUIRED_PAIRS = [
    ("--ink", "--surface", TEXT, "标题与数值"),
    ("--ink", "--bg", TEXT, "标题在页面底色上"),
    ("--ink-2", "--surface", TEXT, "正文"),
    ("--ink-2", "--surface-2", TEXT, "正文在次级底色上"),
    ("--ink-3", "--surface", TEXT, "次要标签（页面上最小的字）"),
    ("--brand", "--surface", TEXT, "链接"),
    ("--brand", "--brand-soft", TEXT, "当前导航项"),
    ("--ok", "--ok-soft", TEXT, "已完成状态"),
    ("--warn", "--warn-soft", TEXT, "过期/受阻状态"),
    ("--danger", "--danger-soft", TEXT, "错误状态"),
    ("--doing", "--doing-soft", TEXT, "进行中状态"),
    ("--idle", "--idle-soft", TEXT, "未启动状态"),
    ("--border-strong", "--surface", UI, "输入框边界"),
    ("--brand", "--surface", UI, "焦点环"),
]

# Hardcoded colours are allowed only inside :root (the token definitions) and in
# translucency helpers that cannot use a token (e.g. rgba overlays).
ALLOWED_HARDCODED = re.compile(r"^\s*(--|/\*|\*)")


def parse_tokens(path: Path) -> dict[str, str]:
    css = path.read_text(encoding="utf-8")
    block = re.search(r":root\s*\{(.*?)\}", css, re.S)
    if not block:
        raise SystemExit(f"no :root block in {path}")
    tokens = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)):
        tokens[name] = value.strip()
    return tokens


def resolve(value: str, tokens: dict[str, str], depth: int = 0) -> str:
    if depth > 8:
        raise SystemExit(f"token cycle at {value!r}")
    ref = re.fullmatch(r"var\((--[\w-]+)\)", value.strip())
    if ref:
        return resolve(tokens[ref.group(1)], tokens, depth + 1)
    return value.strip()


def to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.startswith("#"):
        hexpart = value[1:]
        if len(hexpart) == 3:
            hexpart = "".join(c * 2 for c in hexpart)
        if len(hexpart) != 6:
            raise SystemExit(f"unsupported hex {value!r}")
        return tuple(int(hexpart[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    rgb = re.fullmatch(r"rgba?\(([^)]+)\)", value)
    if rgb:
        parts = [p.strip() for p in rgb.group(1).split(",")]
        return tuple(int(float(p)) for p in parts[:3])  # type: ignore[return-value]
    raise SystemExit(f"unsupported colour {value!r}")


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: str, bg: str) -> float:
    l1 = relative_luminance(to_rgb(fg))
    l2 = relative_luminance(to_rgb(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def check(path: Path, pairs: list[tuple[str, str, float, str]]) -> list[str]:
    tokens = parse_tokens(path)
    failures = []
    for fg_tok, bg_tok, minimum, label in pairs:
        if fg_tok not in tokens:
            failures.append(f"{path.name}: 缺少 token {fg_tok}")
            continue
        if bg_tok not in tokens:
            failures.append(f"{path.name}: 缺少 token {bg_tok}")
            continue
        fg = resolve(tokens[fg_tok], tokens)
        bg = resolve(tokens[bg_tok], tokens)
        r = ratio(fg, bg)
        status = "ok  " if r >= minimum else "FAIL"
        print(f"  [{status}] {label:<24} {fg_tok} on {bg_tok} = {r:5.2f}:1 (需 {minimum})")
        if r < minimum:
            failures.append(f"{path.name}: {fg_tok} on {bg_tok} = {r:.2f}:1 < {minimum}")
    return failures


def check_no_hardcoded(path: Path) -> list[str]:
    """Colours outside :root bypass the palette and therefore this whole check."""
    css = path.read_text(encoding="utf-8")
    end = css.find("}", css.find(":root"))
    body_lines = css[end + 1 :].splitlines()
    offset = css[: end + 1].count("\n") + 1
    bad = []
    for i, line in enumerate(body_lines, start=offset + 1):
        if ALLOWED_HARDCODED.match(line):
            continue
        for hit in re.findall(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b", line):
            bad.append(f"{path.name}:{i}: 硬编码颜色 {hit}（应改用 token）")
    return bad


def main() -> int:
    # Windows runners default stdout to cp1252; the Chinese labels below would raise
    # UnicodeEncodeError and fail the job even though every colour pair passed.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    failures: list[str] = []
    print(f"检查 {BASE_CSS.relative_to(ROOT)}")
    failures += check(BASE_CSS, REQUIRED_PAIRS)
    failures += check_no_hardcoded(BASE_CSS)

    if BOARD_CSS.exists():
        print(f"检查 {BOARD_CSS.relative_to(ROOT)}")
        failures += check(BOARD_CSS, REQUIRED_PAIRS)
        failures += check_no_hardcoded(BOARD_CSS)

    if failures:
        print("\n对比度或调色板不合格：")
        for f in failures:
            print("  -", f)
        return 1
    print("\n全部通过：正文 ≥4.5:1，边界与焦点环 ≥3:1，无硬编码颜色。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
