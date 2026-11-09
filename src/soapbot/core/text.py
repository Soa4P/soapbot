"""Text normalisation shared by every path that shows model output to a human.

Kept in its own module because there are now two such paths: the ordinary reply
stage, and the progressive sender that emits sentences while the model is still
talking. Two copies of the invisible-character table would drift, and the drift would
only be visible as "the streamed messages contain a bidi override the normal ones
strip" — a security difference nobody would look for.

That reasoning turned out to be the smaller half of the problem. The table had *five*
copies by the time it was noticed, and they had already drifted apart: the injection
screen knew about the bidi overrides and the Unicode tag characters, the other three
did not, and none of them covered the Unicode isolate characters. Every path that
screens untrusted text now imports this one.
"""

from __future__ import annotations

import re

#: Characters that are invisible to a human reader but are read by a model, and are
#: used to smuggle instructions past a moderator looking at the same text.
#:
#: A copy that lags is a bypass. The injection screen, the memory vet and the tool-text
#: scrubber each read their own table, so a character missing from the weakest one
#: slips past all three and arrives in the prompt — where the model reads it, even
#: though the regex, which sees an isolate as an ordinary character, does not.
#:
#: Written as ranges rather than as escaped literals on purpose: a literal list of
#: invisible characters in source is itself unreadable, and impossible to review.
INVISIBLE = dict.fromkeys(
    [
        *range(0x200B, 0x2010),  # zero-width space .. right-to-left mark
        *range(0x202A, 0x202F),  # bidi embedding / override, LRM, RLM
        *range(0x2060, 0x2065),  # word joiner, invisible operators, invisible plus
        *range(0x2066, 0x206A),  # LRI / RLI / FSI / PDI — the isolate characters
        0x00AD,  # soft hyphen
        0x061C,  # Arabic letter mark (bidi control)
        0x180E,  # Mongolian vowel separator
        0xFEFF,  # BOM / zero-width no-break space
        *range(0xE0000, 0xE0080),  # Unicode tag characters
    ],
    None,
)

_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_text(text: str) -> str:
    """Strip invisible characters and collapse runs of spaces/tabs."""
    return _MULTI_SPACE.sub(" ", str(text).translate(INVISIBLE))
