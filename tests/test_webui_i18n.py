"""Frontend catalogue consistency, checked from the Python suite.

The frontend has no test runner in this repository (no vitest, and adding one for a few
static files would be more machinery than the check is worth). The properties that
actually matter are set comparisons and text scans over plain files, so they live here
and run in the same pass as everything else.

What this does *not* prove: that the translations read well, or that a layout survives
a longer language. Those need eyes. What it prevents is the class of failure that ships
silently:

* a label rendering as a raw key (``settings.voice.voice``) because one catalogue was
  updated and the other was not;
* a page that was never migrated, so half the console switches language and half does
  not — the failure mode that made the previous "i18n ✅" claim wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "webui" / "src"
LOCALES = WEBUI / "i18n" / "locales"

CJK = re.compile(r"[\u4e00-\u9fff]")
_KEY_RE = re.compile(r"^\s*'([^']+)':", re.MULTILINE)
_USE_RE = re.compile(r"\bt\('([^']+)'")


def _keys(name: str) -> set[str]:
    text = (LOCALES / f"{name}.ts").read_text(encoding="utf-8")
    return set(_KEY_RE.findall(text))


def _vue_files() -> list[Path]:
    return sorted(WEBUI.rglob("*.vue"))


def _split(path: Path) -> tuple[str, str]:
    """Return (script, template). Missing blocks come back empty rather than raising."""
    text = path.read_text(encoding="utf-8")
    script = re.search(r"<script[^>]*>(.*?)</script>", text, re.S)
    template = re.search(r"<template>(.*)</template>\s*(?:<style|$)", text, re.S)
    return (script.group(1) if script else "", template.group(1) if template else text)


def _strip_comments(text: str) -> str:
    """Remove `<!-- -->`, `//` and `/* */` so prose about Chinese is not counted."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r"\s//\s.*$", "", text, flags=re.M)
    return text


# ---------------------------------------------------------------- catalogue shape


def test_both_panel_catalogues_exist() -> None:
    assert (LOCALES / "zh-CN.ts").is_file()
    assert (LOCALES / "en-US.ts").is_file()


def test_catalogues_have_identical_keys() -> None:
    zh = _keys("zh-CN")
    en = _keys("en-US")
    assert zh, "the Chinese catalogue parsed as empty; the pattern no longer matches"
    missing_en = sorted(zh - en)
    missing_zh = sorted(en - zh)
    assert not missing_en, f"keys missing from en-US: {missing_en}"
    assert not missing_zh, f"keys missing from zh-CN: {missing_zh}"


def test_placeholders_match_across_languages() -> None:
    """A `{role}` in one language and `{rol}` in the other loses data silently."""
    zh_text = (LOCALES / "zh-CN.ts").read_text(encoding="utf-8")
    en_text = (LOCALES / "en-US.ts").read_text(encoding="utf-8")

    def placeholders(text: str) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for line in text.splitlines():
            match = re.match(r"^\s*'([^']+)':\s*'(.*)',?\s*$", line)
            if not match:
                continue
            out[match.group(1)] = set(re.findall(r"\{(\w+)\}", match.group(2)))
        return out

    zh = placeholders(zh_text)
    en = placeholders(en_text)
    for key in sorted(set(zh) & set(en)):
        assert zh[key] == en[key], f"placeholder mismatch for {key}: {zh[key]} vs {en[key]}"


def test_no_duplicate_keys() -> None:
    """A duplicated key silently overrides the earlier one, so the first is dead."""
    for name in ("zh-CN", "en-US"):
        text = (LOCALES / f"{name}.ts").read_text(encoding="utf-8")
        keys = _KEY_RE.findall(text)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        assert not duplicates, f"{name}.ts has duplicate keys: {duplicates}"


# ---------------------------------------------------------------- usage in views


def test_every_key_used_by_a_view_exists() -> None:
    """A typo renders the key to the operator, which is worse than a blank.

    Covers every ``.vue`` under ``src`` — views, charts, the shell — because the shell
    and the chart components carry labels of their own and would otherwise be the
    place where a key goes missing unnoticed.
    """
    catalogue = _keys("zh-CN") & _keys("en-US")
    missing: dict[str, list[str]] = {}
    for path in _vue_files() + sorted(WEBUI.rglob("*.ts")):
        # Comments are stripped first: a doc comment that writes `t('...')` as an
        # example is not a usage, and counting it made this check fail for a reason
        # that had nothing to do with the code.
        text = _strip_comments(path.read_text(encoding="utf-8"))
        used = set(_USE_RE.findall(text))
        absent = sorted(used - catalogue)
        if absent:
            missing[str(path.relative_to(WEBUI))] = absent
    assert not missing, f"keys referenced but not defined: {missing}"


def test_no_hardcoded_cjk_in_templates() -> None:
    """The check that the previous "i18n done" claim would have failed.

    Static key checks cannot tell a fully migrated console from a half-migrated one —
    both have valid keys. Scanning for CJK left in a template is what distinguishes
    them.
    """
    offenders: dict[str, list[str]] = {}
    for path in _vue_files():
        _, template = _split(path)
        text = _strip_comments(template)
        hits = [line.strip()[:90] for line in text.splitlines() if CJK.search(line)]
        if hits:
            offenders[str(path.relative_to(WEBUI))] = hits
    assert not offenders, f"untranslated text in templates: {offenders}"


def test_no_hardcoded_cjk_in_script_strings() -> None:
    """Same for values built in script — that is where the stale-notice bugs lived."""
    offenders: dict[str, list[str]] = {}
    for path in _vue_files() + sorted(WEBUI.rglob("*.ts")):
        if path.name in {"zh-CN.ts", "en-US.ts"}:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        hits = [
            match.group(0)[:90]
            for match in re.finditer(r"'[^'\n]*[\u4e00-\u9fff][^'\n]*'", text)
        ]
        if hits:
            offenders[str(path.relative_to(WEBUI))] = hits
    assert not offenders, f"untranslated string literals: {offenders}"


def test_every_nav_key_used_by_the_rail_exists() -> None:
    """The rail builds labels from ``nav.NN``; a typo renders the key to the operator."""
    shell = (WEBUI / "components" / "AppShell.vue").read_text(encoding="utf-8")
    used = set(re.findall(r"key:\s*'(nav\.\d+)'", shell))
    assert used, "could not find nav keys in AppShell.vue"
    missing = sorted(used - _keys("zh-CN"))
    assert not missing, f"nav keys missing from the catalogue: {missing}"
