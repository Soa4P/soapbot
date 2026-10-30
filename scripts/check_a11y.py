"""Four accessibility rules that can be checked without a browser.

Why static
----------
axe-core measures the rendered DOM and needs a browser in CI; this project has no
frontend test runner and is not about to grow one for four assertions. What is left is
the class of defect that is invisible in a mouse-driven demo and total for everyone
else: a control with no accessible name, a click target that cannot be focused, an image
with no alternative, a dialog that never announces itself.

What it cannot catch: focus order, focus trapping, colour of a focus ring, or whether
the name is *good*. Those need the page running, and `docs/verification-matrix.md`
records which of them were walked by hand.

Every finding names file, line and rule, so the fix is a jump rather than a hunt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "webui" / "src"

#: Elements that can carry `@click`. A `div` with a handler is invisible to the keyboard
#: unless it also says what it is (`role`) and admits focus (`tabindex`).
CLICKABLE = ("div", "span", "li", "td", "tr", "section", "article")

TAG = re.compile(r"<(?P<name>[a-zA-Z][\w-]*)(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.S)
#: `{{ ... }}` counts as content: the name comes from i18n at runtime.
MUSTACHE = re.compile(r"\{\{.*?\}\}", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def _has(attrs: str, *names: str) -> bool:
    """True when any of ``names`` is present as an attribute, bare or bound.

    The terminator allows ``.`` so that ``@keydown.enter`` counts as ``@keydown``: a
    modifier narrows a listener, it is not a different attribute.
    """
    for name in names:
        if re.search(
            rf"(^|\s)(:|v-bind:|@|v-on:)?{re.escape(name)}(?=[\s=/>.,]|$)", attrs
        ):
            return True
    return False


def _inner(source: str, start: int, name: str) -> str:
    """Text of an element's children, tags removed, up to its closing tag."""
    close = source.find(f"</{name}", start)
    if close == -1:
        return ""
    body = source[start:close]
    body = TAG.sub("", body)
    return COMMENT.sub("", body).strip()


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    source = path.read_text(encoding="utf-8", errors="replace")
    # Only the <template> block is markup. Scanning the whole file reads a `<button>`
    # mentioned in a code comment as a real element and reports a defect that is not
    # there — the first run of this script did exactly that.
    start = source.find("<template>")
    end = source.rfind("</template>")
    if start != -1 and end != -1:
        source = "\n" * source.count("\n", 0, start) + source[start : end + len("</template>")]
    source = COMMENT.sub(lambda m: " " * len(m.group(0)), source)
    relative = path.relative_to(ROOT)

    for match in TAG.finditer(source):
        name = match.group("name").lower()
        attrs = match.group("attrs")
        line = source.count("\n", 0, match.start()) + 1

        # 1. An icon-only button needs a name of its own.
        if name == "button":
            text = _inner(source, match.end(), "button")
            text = MUSTACHE.sub("x", text)
            text = re.sub(r"<[^>]*>", "", text).strip()
            if not text and not _has(attrs, "aria-label", "aria-labelledby", "title"):
                problems.append(f"{relative}:{line} button 只有图标，没有可访问名称（加 aria-label 或 title）")

        # 2. A click handler on something unfocusable is a keyboard dead end. Two
        #    separate failures: not reachable at all, and reachable but inert. `role` is
        #    deliberately not required — forcing `role="button"` onto a table row hides
        #    its cells from a screen reader, a worse trade than the one it fixes.
        if (
            name in CLICKABLE
            and _has(attrs, "@click", "v-on:click")
            # `@click.self` is the "click outside to dismiss" surface. It is not a
            # control, it must not become a tab stop, and its keyboard equivalent is
            # Esc — which the dialog itself implements.
            and not re.search(r"@click\.(self|outside)|v-on:click\.(self|outside)", attrs)
        ):
            if not _has(attrs, "tabindex"):
                problems.append(f"{relative}:{line} <{name}> 有 @click 但不可聚焦（缺 tabindex）")
            elif not _has(attrs, "@keydown", "@keyup", "v-on:keydown", "v-on:keyup"):
                problems.append(
                    f"{relative}:{line} <{name}> 可聚焦但没有键盘处理（按 Enter 什么也不会发生）"
                )

        # 3. Images need alternatives; decorative ones say so explicitly.
        if name == "img" and not _has(attrs, "alt"):
            problems.append(f"{relative}:{line} <img> 缺 alt")

        # 4. A dialog has to announce itself. `alertdialog` counts: it is what this
        #    codebase uses for confirmations, and skipping it here would leave the one
        #    dialog in the app as the one no rule looks at.
        if name in ("div", "dialog") and _has(
            attrs, "role=\"dialog\"", "role='dialog'", "role=\"alertdialog\"", "role='alertdialog'"
        ):
            if not _has(attrs, "aria-modal"):
                problems.append(f"{relative}:{line} role=dialog 缺 aria-modal")
            if not _has(attrs, "aria-label", "aria-labelledby"):
                problems.append(f"{relative}:{line} role=dialog 缺 aria-label / aria-labelledby")

    return problems


def main() -> int:
    # A Windows console is cp1252 and raises on the first Chinese character. Every
    # check_*.py here reconfigures instead of ASCII-ifying the report; this one forgot,
    # and the Windows job failed on its own output rather than on a defect.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = sorted(VIEWS.rglob("*.vue"))
    problems: list[str] = []
    for path in files:
        problems += check_file(path)

    print(f"检查 {len(files)} 个组件")
    if problems:
        print(f"\n可访问性问题：{len(problems)}")
        for item in problems:
            print("  -", item)
        return 1
    print("\n全部通过：按钮有名称、点击目标可聚焦、图片有替代文本、对话框有语义。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
