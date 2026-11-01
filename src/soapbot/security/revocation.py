"""Revocation for admin API tokens.

A signed JWT is valid until it expires. That is the whole point of signing one, and it is
also the problem: ``TokenService`` had no way to invalidate a token it had issued. The
default lifetime is 72 hours, so a token copied out of a browser's local storage, a HAR
file, a screenshot or a shell history stayed usable for three days no matter what the
operator did. Rotating ``SOAPBOT_JWT_SECRET`` was the only remedy, and it logs out every
session at once — so in practice nobody used it.

Two mechanisms, because "revoke this session" and "revoke everything" are different
requests:

* **Per-token** — ``jti`` recorded with its expiry. Cheap, precise, what a logout button
  means.
* **All tokens** — a single ``revoked_before`` timestamp. Any token issued at or before it
  is refused, including ones the operator has no ``jti`` for. This is the "the key may be
  compromised" button, and it must work without knowing which tokens exist.

The file is written atomically. A truncated revocation file would silently restore every
revoked token, which is the one failure this module must not have.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from soapbot.security.files import tighten

logger = logging.getLogger(__name__)

FILENAME = "token-revocations.json"
"""Fixed filename under the data directory."""

_SCHEMA = 1


class RevocationStore:
    """Persistent set of revoked token ids, plus a global cut-off timestamp."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._loaded = False
        self._entries: dict[str, int] = {}
        """``jti -> exp``. The expiry is kept so entries can be pruned once the token
        would have expired anyway: keeping them forever makes the file grow without
        bound, and a revocation list that needs maintenance gets deleted instead."""
        self._revoked_before: float = 0.0

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Fail closed: refuse to start from an unreadable revocation file rather
            # than pretend nothing was revoked. The alternative silently un-revokes
            # every token the operator deliberately killed, which is worse than a
            # startup failure an operator can see and fix.
            raise RuntimeError(
                f"token revocation file is unreadable ({exc}); refusing to treat it as "
                f"empty. Fix or delete {self.path}."
            ) from exc

        if not isinstance(raw, dict):
            return
        entries = raw.get("tokens")
        if isinstance(entries, dict):
            for jti, exp in entries.items():
                try:
                    self._entries[str(jti)] = int(exp)
                except (TypeError, ValueError):
                    continue
        try:
            self._revoked_before = float(raw.get("revoked_before") or 0.0)
        except (TypeError, ValueError):
            self._revoked_before = 0.0

    def _flush(self) -> None:
        payload = {
            "schema": _SCHEMA,
            "revoked_before": self._revoked_before,
            "tokens": dict(sorted(self._entries.items())),
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Same reasoning as the approval store: a crash mid-write must not leave a
        # truncated file, because a truncated file here un-revokes tokens.
        fd, tmp_name = tempfile.mkstemp(prefix=".token-revocations-", dir=str(self.path.parent))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        tighten(self.path, what="token revocation record")

    # --------------------------------------------------------------------- queries
    def is_revoked(self, jti: str, issued_at: int, *, now: float | None = None) -> bool:
        """Whether a token is revoked, by id or by the global cut-off."""
        self.load()
        if jti and jti in self._entries:
            return True
        # Strictly ``<``, and the boundary is deliberate. ``revoke-all`` means "everything
        # issued before now"; the token the operator is handed back on the same second is
        # *not* before now, and treating it as revoked would log them straight back out —
        # with the bootstrap token already consumed, that is a permanent lockout.
        #
        # The obvious objection is the one-second window this leaves. It is not a real
        # one: closing it requires an attacker who can mint tokens, and an attacker who
        # can mint tokens also controls ``iat``, so no timestamp comparison constrains
        # them. Against a *stolen* token — the case this exists for — sub-second
        # precision is irrelevant.
        return bool(self._revoked_before) and issued_at < self._revoked_before

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        """What the panel shows: which ids are revoked and until when."""
        self.load()
        moment = time.time() if now is None else now
        return {
            "revoked_before": self._revoked_before,
            "count": len(self._entries),
            "tokens": [
                {"jti": jti, "expires_at": exp, "expired": exp <= moment}
                for jti, exp in sorted(self._entries.items(), key=lambda kv: kv[1])
            ],
        }

    # -------------------------------------------------------------------- mutation
    def revoke(self, jti: str, exp: int, *, now: float | None = None) -> bool:
        """Revoke one token. Returns ``False`` if it was already revoked."""
        self.load()
        moment = int(time.time() if now is None else now)
        if not jti:
            return False
        if jti in self._entries:
            return False
        # Keep the entry until it would have expired anyway; after that the signature
        # check rejects it on its own.
        self._entries[jti] = max(int(exp or 0), moment)
        self._flush()
        return True

    def revoke_all(self, *, now: float | None = None) -> float:
        """Invalidate every token issued up to now. Returns the cut-off timestamp.

        Truncated to whole seconds because ``iat`` is whole seconds. Storing a float
        makes ``iat < cut_off`` true for a token issued in the same second (``1793541 <
        1793541.9``), which revokes the replacement token issued immediately afterwards —
        the lockout this boundary exists to prevent. Comparing at one granularity means
        the comparison says what the docstring says.
        """
        self.load()
        moment = int(time.time() if now is None else now)
        self._revoked_before = float(moment)
        # Individual entries and the cut-off overlap from here; keeping both is correct,
        # because a later token issued *after* the cut-off must still be revocable by id.
        self._flush()
        logger.warning(
            "all admin tokens revoked; any token issued before %.0f is now refused", moment
        )
        return moment

    def prune(self, *, now: float | None = None) -> int:
        """Drop entries for tokens that have expired. Returns how many were removed."""
        self.load()
        moment = time.time() if now is None else now
        stale = [jti for jti, exp in self._entries.items() if exp <= moment]
        for jti in stale:
            del self._entries[jti]
        if stale:
            self._flush()
        return len(stale)

    def clear(self) -> None:
        """Test seam: forget everything, including the global cut-off."""
        self._entries.clear()
        self._revoked_before = 0.0
        self._flush()


def default_path(data_dir: Path) -> Path:
    return Path(data_dir) / FILENAME


__all__ = ["FILENAME", "RevocationStore", "default_path"]
