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
* **The bootstrap token is single-use and dies with the process.** It exists to let a
  fresh install obtain a token without a second channel. Keeping it valid forever
  would make the file that logs it a permanent credential.
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

import jwt

from soapbot.config import settings
from soapbot.security.files import write_private_file

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
    ) -> None:
        self._secret_file = secret_file or (settings.data_dir / "jwt.key")
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

        return TokenClaims(
            subject=str(payload.get("sub", "")),
            role=str(payload.get("role", "")),
            issued_at=int(payload.get("iat", 0)),
            expires_at=int(payload.get("exp", 0)),
            token_id=str(payload.get("jti", "")),
        )


class BootstrapToken:
    """Single-use initial credential.

    Generated when ``SOAPBOT_INIT_TOKEN`` is not set and printed to the log once. The
    alternative — requiring the operator to invent a secret before first start —
    pushes people towards a hardcoded default, which is worse than a random value in
    a log they already control.
    """

    def __init__(self, token: str = "") -> None:
        self._token = token or secrets.token_urlsafe(24)
        self._generated = not token
        self._consumed = False

    @property
    def generated(self) -> bool:
        return self._generated

    @property
    def consumed(self) -> bool:
        return self._consumed

    def reveal(self) -> str:
        """Return the raw token.

        Exists solely so the application can write it to a mode-0600 file on first
        start. Nothing that serves an HTTP response may call it, and
        ``/api/auth/status`` reports only whether login is still possible, never the
        value.
        """
        return self._token

    def redeem(self, candidate: str) -> bool:
        """Consume the token if ``candidate`` matches.

        Constant-time comparison, and the token is marked consumed *before* returning,
        so two concurrent requests cannot both succeed on the same bootstrap secret.
        """
        if self._consumed or not candidate:
            return False
        if not hmac.compare_digest(candidate.strip(), self._token):
            return False
        self._consumed = True
        return True


__all__ = [
    "ALGORITHM",
    "AUDIENCE",
    "MIN_SECRET_BYTES",
    "BootstrapToken",
    "TokenClaims",
    "TokenError",
    "TokenService",
]
