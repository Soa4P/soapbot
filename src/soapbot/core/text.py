"""Text normalisation shared by every path that shows model output to a human.

Kept in its own module because there are now two such paths: the ordinary reply
stage, and the progressive sender that emits sentences while the model is still
talking. Two copies of the invisible-character table would drift, and the drift would
only be visible as "the streamed messages contain a bidi override the normal ones
strip" — a security difference nobody would look for.
"""

from __future__ import annotations

import re

#: Characters that are invisible to a human reader but are read by a model, and are
#: used to smuggle instructions past a moderator looking at the same text.
INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"),
    None,
)

_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_text(text: str) -> str:
    """Strip invisible characters and collapse runs of spaces/tabs."""
    return _MULTI_SPACE.sub(" ", str(text).translate(INVISIBLE))
