"""Admin API tokens: JWT issuance, verification, and the one-time bootstrap token.

Threat model
------------
The management API can load plugins (in-process code execution), rewrite persona
files and approve spending. Until this module existed the only control was
"loopback", which is a property of the *bind address* plus a client-IP check — one
``SOAPBOT_HOST=0.0.0.0`` away from unauthenticated remote code execution. A reverse
proxy that forwards to ``127.0.0.1`` defeats the IP check entirely, because the
proxied request genuinely arrives from loopback.

So: possession of a signed token is the control. Source address is a convenience for
local development, not an authorization decision.

Design decisions worth stating
------------------------------
* **HS256 with a persisted secret.** Asymmetric signing buys nothing here: the
  verifier is the same process that issues, so a public key would have to be
  distributed to clients that already hold a bearer token.
* **The secret must be at least 32 bytes.** A short HMAC key is offline-brute-forced
  from a single captured token. Refusing to start with a weak one is the only
  moment the operator will actually fix it.
* **The bootstrap token is single-use, and stays valid across restarts until used.**
  It exists to let a fresh install obtain a token without a second channel. It used to
  be recreated on *every* process start, which silently invalidated whatever the
  operator had written down: six restarts produced six different tokens, each one
  overwriting the file, with no log line saying the old value was dead. Now the
  unredeemed value is reused from disk, and redeeming it deletes the file and leaves a
  marker so a restart cannot resurrect it. A new one requires an explicit
  ``soapbot token --reset`` on the host.
* **Claims are not permissions.** The token says "this is the operator's API client".
  It never says "user 12345 is an owner in group 6789" — chat privileges are derived
  from configuration on every message (``soapbot.security.principal``), because a
  token is a bearer artefact and a chat identity is not.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import jwt

from soapbot.config import settings
from soapbot.security.files import write_private_file

if TYPE_CHECKING:  # pragma: no cover - typing only
    from soapbot.security.revocation import RevocationStore

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
AUDIENCE = "soapbot-api"
ISSUER = "soapbot"
MIN_SECRET_BYTES = 32
"""HS256 keys shorter than the hash output add nothing and are brute-forceable."""

_CLOCK_LEEWAY_SECONDS = 30
"""Tolerated clock skew. Well under the token lifetime, so it cannot extend a
revoked-by-expiry token usefully."""


class TokenError(RuntimeError):
    """Any failure to issue or verify a token."""


@dataclass(slots=True, frozen=True)
class TokenClaims:
    subject: str
    role: str
    issued_at: int
    expires_at: int
    token_id: str

    @property
    def ttl_remaining(self) -> int:
        return max(0, self.expires_at - int(time.time()))


def _read_or_create_secret(path: Path) -> bytes:
    """Load the signing key, creating it with restrictive permissions if absent.

    Same reasoning as ``security.crypto`` for the Fernet key; the platform caveat is
    documented in ``security.files``.
    """
    if path.exists():
        data = path.read_bytes().strip()
        if len(data) < MIN_SECRET_BYTES:
            raise TokenError(
                f"JWT secret at {path} is shorter than {MIN_SECRET_BYTES} bytes; "
                "delete it to regenerate, or set SOAPBOT_JWT_SECRET"
            )
        return data

    key = secrets.token_urlsafe(48).encode("ascii")
    write_private_file(path, key, what="JWT signing key")
    logger.info("generated JWT signing key at %s", path)
    return key


class TokenService:
    """Issues and verifies admin API tokens."""

    def __init__(
        self,
        *,
        secret: str = "",
        ttl_hours: int = 72,
        secret_file: Path | None = None,
        revocations: RevocationStore | None = None,
    ) -> None:
        self._secret_file = secret_file or (settings.data_dir / "jwt.key")
        # ``None`` keeps verify() stateless, so tests and embedded callers that never
        # construct a store behave exactly as before. The deployment path always
        # supplies one — see ``app._init_auth``: a revocation list nobody consults is
        # not a revocation mechanism, it is a file.
        self._revocations = revocations
        if secret:
            raw = secret.encode("utf-8")
            if len(raw) < MIN_SECRET_BYTES:
                raise TokenError(
                    f"SOAPBOT_JWT_SECRET must be at least {MIN_SECRET_BYTES} characters "
                    f"(got {len(raw)})"
                )
            self._key = raw
            self.secret_source = "configured"
        else:
            self._key = _read_or_create_secret(self._secret_file)
            self.secret_source = f"file:{self._secret_file}"
        self.ttl_seconds = int(max(1, ttl_hours) * 3600)

    # ------------------------------------------------------------------ issuance
    def issue(self, subject: str = "operator", *, role: str = "owner") -> tuple[str, TokenClaims]:
        now = int(time.time())
        exp = now + self.ttl_seconds
        jti = secrets.token_urlsafe(12)
        payload = {
            "sub": subject,
            "role": role,
            "iat": now,
            "exp": exp,
            "nbf": now,
            "jti": jti,
            "aud": AUDIENCE,
            "iss": ISSUER,
        }
        token = jwt.encode(payload, self._key, algorithm=ALGORITHM)
        claims = TokenClaims(
            subject=subject, role=role, issued_at=now, expires_at=exp, token_id=jti
        )
        logger.info("issued admin token subject=%s expires_in=%ds", subject, self.ttl_seconds)
        return token, claims

    # ------------------------------------------------------------- verification
    def verify(self, token: str) -> TokenClaims:
        """Decode and validate a token, or raise :class:`TokenError`.

        ``require`` is not decoration: without it a token minted by an older version
        (or by an attacker who found another HS256 consumer sharing this key) could
        omit ``exp`` and never expire.
        """
        if not token:
            raise TokenError("empty token")
        try:
            payload = jwt.decode(
                token,
                self._key,
                algorithms=[ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=_CLOCK_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "jti", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("token expired") from exc
        except jwt.InvalidTokenError as exc:
            # Deliberately coarse: telling a caller *which* validation failed turns
            # the endpoint into an oracle for crafting a valid token.
            raise TokenError("invalid token") from exc

        claims = TokenClaims(
            subject=str(payload.get("sub", "")),
            role=str(payload.get("role", "")),
            issued_at=int(payload.get("iat", 0)),
            expires_at=int(payload.get("exp", 0)),
            token_id=str(payload.get("jti", "")),
        )

        # Revocation is checked *after* the signature and claims: an unsigned or expired
        # token must not be reported as "revoked", because that would let a caller
        # distinguish a token we once issued from one we never did.
        if self._revocations is not None and self._revocations.is_revoked(
            claims.token_id, claims.issued_at
        ):
            raise TokenError("token revoked")
        return claims


BOOTSTRAP_FILE = "init_token.txt"
BOOTSTRAP_REDEEMED = "init_token.redeemed"
"""`init_token.redeemed` is a marker, not a secret: it records that the credential was
used, so a later process start does not treat "no token file" as a fresh install and
mint a replacement. Without it, deleting the file after use would silently re-enable
login on every restart — the one thing a single-use credential must never do.
"""


class BootstrapToken:
    """Single-use initial credential, stable across restarts until redeemed.

    ``path`` / ``redeemed_marker`` are optional so tests and callers that supply a
    literal token (``BootstrapToken("b")``) keep exactly the old in-memory behaviour.
    Only tokens created by :func:`bootstrap_for_data_dir` own files.
    """

    def __init__(
        self,
        token: str = "",
        *,
        generated: bool | None = None,
        enabled: bool = True,
        path: Path | None = None,
        redeemed_marker: Path | None = None,
    ) -> None:
        self._token = token or secrets.token_urlsafe(24)
        self._generated = (not token) if generated is None else generated
        self._enabled = enabled
        self._consumed = False
        self._path = path
        self._redeemed_marker = redeemed_marker

    @property
    def generated(self) -> bool:
        return self._generated

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def available(self) -> bool:
        return self._enabled and not self._consumed

    @property
    def state(self) -> str:
        """What the status endpoint may report — never the value itself."""
        if self._consumed or not self._enabled:
            return "redeemed"
        return "available"

    def reveal(self) -> str:
        """Return the raw token.

        Exists solely so the CLI can print it. Nothing that serves an HTTP response
        may call it, and ``/api/auth/status`` reports only whether login is still
        possible, never the value.
        """
        return self._token

    def redeem(self, candidate: str) -> bool:
        """Consume the token if ``candidate`` matches.

        Constant-time comparison, and the token is marked consumed *before* returning,
        so two concurrent requests cannot both succeed on the same bootstrap secret.
        """
        if not self.available or not candidate:
            return False
        if not hmac.compare_digest(candidate.strip(), self._token):
            return False
        self._consumed = True
        self._destroy_persisted_copy()
        return True

    def _destroy_persisted_copy(self) -> None:
        """Remove the on-disk credential and record that it was used.

        Order matters: write the marker FIRST. If the marker cannot be written, leave
        the token file in place rather than deleting it — otherwise the next start sees
        "no file, no marker", concludes this is a fresh install, and mints a new
        credential on its own. That would quietly undo the single-use guarantee.
        """
        if self._path is None:
            return
        if self._redeemed_marker is not None:
            try:
                write_private_file(
                    self._redeemed_marker, b"redeemed\n", what="bootstrap redeemed marker"
                )
            except OSError as exc:  # pragma: no cover - full disk / ACL
                logger.error(
                    "could not record bootstrap redemption at %s (%s); keeping the "
                    "token file so login is not silently re-enabled",
                    self._redeemed_marker,
                    exc,
                )
                return
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - Windows ACL / sharing violation
            logger.warning(
                "could not delete the redeemed bootstrap token at %s (%s); the "
                "redeemed marker still prevents reuse after a restart",
                self._path,
                exc,
            )

    def regenerate(self) -> str:
        """Mint a fresh single-use credential in the **running** process.

        ``reset_bootstrap`` writes the files for a restart, but the live process keeps
        its old ``_consumed`` object, so the new value is refused until a restart. That
        is fine for a CLI recovery and useless for "revoke everything": the operator
        needs a way back in *now*. This method updates both the files and this object.

        Order matters. Write the new token file first, then remove the redeemed marker:
        a crash in between must leave a usable credential on disk, not a state that a
        later start reads as "fresh install" and silently rotates again. An instance
        without files (an explicitly configured ``SOAPBOT_INIT_TOKEN``) rotates only
        its in-memory value; a restart then returns to the configured one, which is the
        operator's own lifecycle decision.
        """
        value = secrets.token_urlsafe(24)
        if self._path is not None:
            write_private_file(
                self._path, value.encode("utf-8"), what="bootstrap token"
            )
            if self._redeemed_marker is not None:
                self._redeemed_marker.unlink(missing_ok=True)
        self._token = value
        self._consumed = False
        self._enabled = True
        self._generated = True
        logger.info("bootstrap credential rotated for the running process")
        return value


def bootstrap_for_data_dir(data_dir: Path, configured: str = "") -> BootstrapToken:
    """Load the credential for this install, creating one only on a *fresh* install.

    The three states are deliberately distinguished by files, not by process memory:

    * token file present, no marker  -> reuse it (a restart must not rotate the value)
    * marker present                 -> already redeemed; login stays closed
    * neither present                -> first start; generate and persist one

    ``configured`` bypasses the files: an operator who set ``SOAPBOT_INIT_TOKEN``
    explicitly owns that value and its lifecycle.
    """
    path = data_dir / BOOTSTRAP_FILE
    marker = data_dir / BOOTSTRAP_REDEEMED

    if configured:
        return BootstrapToken(configured, generated=False)
    if marker.exists():
        return BootstrapToken("", generated=False, enabled=False)
    if path.is_file():
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            return BootstrapToken(
                value, generated=False, path=path, redeemed_marker=marker
            )
        # An empty or unreadable file is not a credential; treat this as a fresh
        # install and rewrite it rather than leaving the operator with no way in.

    value = secrets.token_urlsafe(24)
    write_private_file(path, value.encode("utf-8"), what="bootstrap token")
    return BootstrapToken(value, generated=True, path=path, redeemed_marker=marker)


def reset_bootstrap(data_dir: Path) -> str:
    """Explicitly mint a new credential. The only way back in after redemption.

    The running process still holds its old in-memory object, so the operator must
    restart the service before the new value is accepted. The CLI says so.
    """
    path = data_dir / BOOTSTRAP_FILE
    marker = data_dir / BOOTSTRAP_REDEEMED
    marker.unlink(missing_ok=True)
    value = secrets.token_urlsafe(24)
    write_private_file(path, value.encode("utf-8"), what="bootstrap token")
    return value


__all__ = [
    "ALGORITHM",
    "AUDIENCE",
    "MIN_SECRET_BYTES",
    "BootstrapToken",
    "TokenClaims",
    "TokenError",
    "TokenService",
]
