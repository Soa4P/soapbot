"""Message catalogs: flat JSON, loaded once, with a visible fallback chain.

Why JSON files and not gettext ``.po``: the catalog is a few hundred short strings in
two languages, updated by hand. ``.po`` adds a compile step (``msgfmt``) that has to be
remembered before every release and that leaves the repo holding a binary-ish artifact
next to its source. ``json`` is diffable, has no build step, and ``json.dumps`` cannot
silently mangle the format.

**Scope, deliberately narrow.** Only text a *human outside the project* reads is
translated: bot replies in the chat, and API ``detail`` strings that a panel operator
sees. Logging and exception messages stay English. Translating logs would turn one
event into different strings per locale, which breaks ``grep`` and every alert rule
built on it — the operator searches for "pipeline crashed", not for a phrase that
depends on a setting. ``tests/test_i18n.py`` enforces that boundary by scanning for
``t(`` inside logger calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The language a message falls back to. Also the language the project's own copy is
#: written in, so a missing translation is readable rather than a raw key.
DEFAULT_LOCALE = "zh-CN"

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

#: Keys already reported as missing. A missing key inside a per-message code path
#: would otherwise log once per incoming message — turning a small catalogue gap into
#: a log flood that hides the real errors next to it.
_warned: set[tuple[str, str]] = set()

_catalogues: dict[str, dict[str, str]] = {}


def available_locales() -> list[str]:
    """Locales that have a catalogue on disk, sorted for stable UI ordering."""
    if not LOCALES_DIR.is_dir():
        return [DEFAULT_LOCALE]
    found = sorted(p.stem for p in LOCALES_DIR.glob("*.json"))
    return found or [DEFAULT_LOCALE]


def _load(locale: str) -> dict[str, str]:
    """Load and cache one catalogue. A broken file is a bug, not an operator error.

    A malformed catalogue raises instead of silently loading empty: an empty catalogue
    would make *every* string fall back to Chinese, which looks like "translation
    unfinished" rather than "the JSON has a trailing comma", and the real cause would
    be invisible right up until someone diffed the file.
    """
    if locale in _catalogues:
        return _catalogues[locale]

    path = LOCALES_DIR / f"{locale}.json"
    if not path.is_file():
        _catalogues[locale] = {}
        return _catalogues[locale]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"message catalogue {path.name} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"message catalogue {path.name} must be a JSON object")

    flat = {str(k): str(v) for k, v in data.items()}
    _catalogues[locale] = flat
    return flat


def resolve(key: str, locale: str) -> str:
    """Return the message for ``key``, walking the fallback chain.

    Order: requested locale, then ``DEFAULT_LOCALE``, then the key itself. Returning
    the key (rather than an empty string) is what makes a missing string obvious in a
    screenshot instead of showing a blank gap that could be a layout bug.
    """
    for candidate in (locale, DEFAULT_LOCALE):
        catalogue = _load(candidate)
        if key in catalogue:
            return catalogue[key]

    marker = (locale, key)
    if marker not in _warned:
        _warned.add(marker)
        logger.warning("i18n key missing locale=%s key=%s", locale, key)
    return key


def translate(key: str, locale: str, /, **params: Any) -> str:
    """``resolve`` plus ``str.format`` interpolation.

    A missing placeholder is a template bug: ``KeyError``/``IndexError`` from
    ``format`` would surface as a crash in the middle of building a reply. Caught and
    returned unformatted so the message still goes out and the defect is visible.
    """
    template = resolve(key, locale)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        logger.warning("i18n template mismatch key=%s locale=%s", key, locale)
        return template


def reset_cache() -> None:
    """Drop loaded catalogues and the missing-key memory. For tests only."""
    _catalogues.clear()
    _warned.clear()
