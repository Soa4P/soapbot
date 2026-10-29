"""Backend message translation for text that leaves the process.

Only two kinds of string belong here: replies the bot sends into a chat, and API
``detail`` messages an operator reads in the panel. Logs and exception text stay
English on purpose — see ``catalog.py`` for the reasoning.

Usage::

    from soapbot.i18n import t

    ctx.model_reply = t("injection.refusal", locale=ctx.locale)

``locale`` is a parameter rather than ambient global state. A single bot process can
serve two groups in two languages, and a module-level "current locale" would make the
reply depend on whichever request happened to set it last — the classic
thread-local-that-is-not-actually-per-request bug.
"""

from __future__ import annotations

from soapbot.i18n.catalog import (
    DEFAULT_LOCALE,
    available_locales,
    reset_cache,
    resolve,
    translate,
)

__all__ = ["DEFAULT_LOCALE", "available_locales", "reset_cache", "resolve", "t"]


def t(key: str, locale: str | None = None, /, **params: object) -> str:
    """Translate ``key`` for ``locale``, falling back to the default language.

    A ``None`` or empty locale means "the default", which is the right answer when a
    caller genuinely has no preference (a startup banner, an unattributed API error).
    """
    return translate(key, locale or DEFAULT_LOCALE, **params)
