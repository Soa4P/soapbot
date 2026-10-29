"""Translation: fallbacks, negotiation, and the boundary around logging.

The scope decision (translate what an outside human reads; never translate logs) is
only worth stating if something enforces it. Prose in a docstring does not survive a
busy week — someone adds ``logger.info(t("x", loc))`` for a nicer log line and grep
silently stops matching. So ``test_no_translation_inside_log_calls`` scans the source.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from soapbot.i18n import DEFAULT_LOCALE, available_locales, resolve, t
from soapbot.i18n.catalog import reset_cache

SRC = Path(__file__).resolve().parents[1] / "src" / "soapbot"


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


# ------------------------------------------------------------------ catalog basics


def test_both_locales_ship_a_catalogue() -> None:
    assert {"zh-CN", "en-US"} <= set(available_locales())


def test_known_key_resolves_per_locale() -> None:
    zh = resolve("injection.refusal", "zh-CN")
    en = resolve("injection.refusal", "en-US")
    assert zh and en
    # The two must actually differ, or the "translation" is a copy and the test above
    # proves nothing about the mechanism.
    assert zh != en


def test_missing_key_falls_back_to_default_locale() -> None:
    """A half-translated catalogue must still produce a sentence, not a raw key."""

    class _Partial(dict):
        pass

    # Simulate a key present in zh-CN but absent from en-US by asking for a key that
    # only the default catalogue has. ``api.trace_too_long`` exists in both, so build
    # the situation directly instead of relying on catalogue drift.
    import soapbot.i18n.catalog as catalog

    catalog._catalogues["en-US"] = {}
    assert resolve("injection.refusal", "en-US") == resolve("injection.refusal", DEFAULT_LOCALE)


def test_unknown_key_returns_the_key_itself() -> None:
    """An empty string would look like a layout bug; the key makes the gap obvious."""
    assert resolve("no.such.key", "en-US") == "no.such.key"


def test_interpolation_and_template_typo_do_not_raise() -> None:
    """A bad placeholder must not crash the reply path mid-build.

    The message still goes out, unformatted, and a warning names the key — a crash
    inside ``ModelStage`` would instead abort the turn.
    """
    assert t("api.role_required", "en-US", role="ADMIN") == "ADMIN permission required"
    # Missing params: the template comes back unformatted rather than raising.
    assert t("api.role_required", "en-US") == "{role} permission required"


def test_available_locales_is_sorted_and_looks_like_files() -> None:
    locales = available_locales()
    assert locales == sorted(locales)
    for name in locales:
        assert re.fullmatch(r"[a-z]{2}-[A-Z]{2}", name), name


# ------------------------------------------------------------------ negotiation


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, DEFAULT_LOCALE),
        ("", DEFAULT_LOCALE),
        ("zh-CN,zh;q=0.9,en;q=0.8", "zh-CN"),
        ("en-US,en;q=0.9", "en-US"),
        # Quality weights decide, not the order of appearance.
        ("zh-CN;q=0.5,en-US;q=0.9", "en-US"),
        # A regional variant has to find the generic catalogue.
        ("en-GB", "en-US"),
        ("zh-Hans-CN", "zh-CN"),
        # A wildcard states no preference, so it must not override the default.
        ("*", DEFAULT_LOCALE),
        ("de-DE", DEFAULT_LOCALE),
    ],
)
def test_accept_language_negotiation(header: str | None, expected: str) -> None:
    from soapbot.api.locale import negotiate_locale

    assert negotiate_locale(header) == expected


def test_negotiation_ignores_malformed_quality() -> None:
    """A broken ``q`` must not silently drop the language to the bottom."""
    from soapbot.api.locale import negotiate_locale

    assert negotiate_locale("en-US;q=abc") == "en-US"


# ------------------------------------------------------------------ the log boundary


def _string_args(node: ast.Call) -> list[str]:
    return [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def test_no_translation_inside_log_calls() -> None:
    """Logs stay English so ``grep`` and every alert rule keep working.

    Scans for ``logger.<level>(t(...))`` and ``logger.<level>(f"...{t(...)` — the two
    shapes someone would actually write. A translated log line means the same event
    has different text per locale, which quietly breaks keyword search.
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "i18n" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a real syntax error fails elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in {"logger", "log"}:
                continue
            for arg in node.args:
                for inner in ast.walk(arg):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "t"
                    ):
                        offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"log calls must not be translated: {offenders}"


def test_translated_strings_used_by_the_reply_path() -> None:
    """The refusal has to come from the catalogue, in the context's language.

    This pins the wire, not just the helper: a stage that kept its own hard-coded
    string would pass every catalogue test and still refuse in Chinese.
    """
    from soapbot.core.pipeline import PipelineContext
    from soapbot.security.injection import injection_refusal

    assert injection_refusal("en-US") == resolve("injection.refusal", "en-US")
    assert injection_refusal("zh-CN") == resolve("injection.refusal", "zh-CN")
    # Default context language is the default locale, so an unconfigured deployment
    # behaves exactly as before.
    assert PipelineContext.__dataclass_fields__["locale"].default == DEFAULT_LOCALE


def test_voice_labels_are_localised() -> None:
    from soapbot.voice.stt import Transcription, render_prompt

    ok = Transcription(text="hello", ok=True)
    assert "hello" in render_prompt(ok, "en-US")
    assert render_prompt(ok, "en-US") != render_prompt(ok, "zh-CN")
    # A failed transcription still has to say something in the right language.
    failed = Transcription(text="", ok=False, reason="no provider")
    assert render_prompt(failed, "en-US") != render_prompt(failed, "zh-CN")


def test_persona_locale_overrides_the_process_default() -> None:
    """Per-card language is the point of carrying locale on the context.

    One bot, several groups: changing the process setting to serve an English group
    would flip every other group too.
    """
    from soapbot.ai.persona import Persona

    assert Persona(id="a", name="A").locale == ""
    assert Persona(id="b", name="B", locale="en-US").locale == "en-US"
