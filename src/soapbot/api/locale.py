"""Pick a language for API ``detail`` strings from the request itself.

The panel is the only consumer, and it sends ``Accept-Language`` like any browser.
Using that header (rather than a stored setting) keeps one API serving two operators
in two languages — an English-speaking admin and a Chinese-speaking one can open the
same dashboard and each get messages they can read.

Deliberately simple matching: the project has two catalogues, so the only decision is
"is Chinese among the accepted languages, and at what priority". A full BCP-47
negotiator would be more correct and would also be a dependency for a two-item list.
"""

from __future__ import annotations

from fastapi import Request

from soapbot.i18n import DEFAULT_LOCALE, available_locales

#: Languages treated as "the Chinese catalogue". Matched by prefix, so ``zh``,
#: ``zh-CN``, ``zh-Hans-CN`` all land here without a table of aliases.
_CHINESE_PREFIX = "zh"


def negotiate_locale(header: str | None) -> str:
    """Return a locale present in the catalogues, given an ``Accept-Language`` value.

    Order is decided by the header's own ``q`` weights, which is what a browser means
    by listing ``en-US;q=0.9, zh-CN;q=0.8``. Wildcards are ignored: ``*`` says nothing
    about preference, so it must not silently win over an absent header.
    """
    known = set(available_locales())
    if not header:
        return DEFAULT_LOCALE

    parsed: list[tuple[float, str]] = []
    for part in header.split(","):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip()
        if not tag or tag == "*":
            continue
        quality = 1.0
        for param in params.split(";"):
            name, _, value = param.strip().partition("=")
            if name.strip() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 1.0
        parsed.append((quality, tag))

    # Stable sort: equal q-values keep the client's original order, which is the
    # documented tie-break and avoids making the answer depend on dict ordering.
    parsed.sort(key=lambda item: item[0], reverse=True)

    for _, tag in parsed:
        lowered = tag.lower()
        if lowered.startswith(_CHINESE_PREFIX):
            candidate = "zh-CN"
        else:
            # Take the primary subtag: ``en-GB`` should find ``en-US``.
            primary = lowered.split("-")[0]
            candidate = next((c for c in known if c.lower().startswith(primary)), "")
        if candidate and candidate in known:
            return candidate

    return DEFAULT_LOCALE


def request_locale(request: Request) -> str:
    """Convenience wrapper for endpoints that need to translate a ``detail``."""
    return negotiate_locale(request.headers.get("accept-language"))


