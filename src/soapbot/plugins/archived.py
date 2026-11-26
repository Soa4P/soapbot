"""Withdrawn plugins: the catalogue's archived list, fetched and surfaced (S-SUP-08).

The index already carries two safety signals — a blocklist and per-version digests — and
the host honours both on *install*. Neither answers a different question: "I have this
plugin installed, has the maintainer withdrawn it?"

That matters because withdrawal is the maintainer's only remedy short of publishing a
block for an exact version. A plugin removed for a reason that is not version-specific
(abandoned, licence problem, a capability the marketplace no longer accepts) keeps working
silently on every machine that installed it, and the operator has no way to learn about it
from the panel.

What this module does **not** do: uninstall, disable, or block anything. Withdrawal is a
statement, and an operator may well decide a withdrawn plugin is still fine for them — the
same position the host takes on manifest drift. It is displayed, attributed, and only then
acted on by a human.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Filename inside the index repository.
ARCHIVED_FILENAME = "archived_plugins.json"

#: A reason is a sentence, not a log file.
MAX_REASON_CHARS = 300


def index_archived_url(catalogue_url: str) -> str:
    base = catalogue_url.rsplit("/", 1)[0]
    return f"{base}/{ARCHIVED_FILENAME}"


def parse_archived(payload: Any) -> dict[str, str]:
    """``name -> reason`` from the catalogue's archived list.

    Tolerant by construction: this file is optional (an index that never withdrew
    anything has no reason to publish it), so a missing or malformed entry yields an empty
    map rather than an error the panel would have to render.
    """
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("archived")
    if not isinstance(rows, list):
        return {}
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        reason = str(row.get("reason") or "").strip()[:MAX_REASON_CHARS]
        out[name] = reason or "目录已撤回（未给出原因）"
    return out


def load_local(path: Path) -> dict[str, str]:
    """Read ``archived_plugins.json`` from disk; missing file means "none"."""
    try:
        return parse_archived(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}
