"""Frontend catalogue consistency, checked from the Python suite.

The frontend has no test runner in this repository (no vitest, and adding one for two
static files would be more machinery than the check is worth). The property that
actually matters — every key exists in both languages — is a set comparison over two
text files, so it can live here and run in the same pass as everything else.

What this does *not* prove: that the translations read well, or that a view uses a key
correctly. Those need eyes. What it prevents is the specific failure that ships
silently: a label that renders as a raw key like ``settings.voice.voice`` because the
English file was updated and the Chinese one was not.
"""

from __future__ import annotations

import re
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[1] / "webui" / "src" / "i18n" / "locales"

_KEY_RE = re.compile(r"^\s*'([^']+)':", re.MULTILINE)


def _keys(name: str) -> set[str]:
    text = (LOCALES / f"{name}.ts").read_text(encoding="utf-8")
    return set(_KEY_RE.findall(text))


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


def test_every_nav_key_used_by_the_rail_exists() -> None:
    """The rail builds labels from ``nav.NN``; a typo renders the key to the operator."""
    shell = (
        Path(__file__).resolve().parents[1] / "webui" / "src" / "components" / "AppShell.vue"
    ).read_text(encoding="utf-8")
    used = set(re.findall(r"key:\s*'(nav\.\d+)'", shell))
    assert used, "could not find nav keys in AppShell.vue"
    catalogue = _keys("zh-CN")
    missing = sorted(used - catalogue)
    assert not missing, f"nav keys missing from the catalogue: {missing}"


def test_settings_page_keys_exist() -> None:
    """Pins the page whose labels are easiest to forget, because it is the newest."""
    view = (
        Path(__file__).resolve().parents[1]
        / "webui"
        / "src"
        / "views"
        / "SettingsView.vue"
    ).read_text(encoding="utf-8")
    used = set(re.findall(r"t\('([^']+)'\)", view))
    catalogue = _keys("zh-CN")
    missing = sorted(used - catalogue)
    assert not missing, f"settings page references missing keys: {missing}"
