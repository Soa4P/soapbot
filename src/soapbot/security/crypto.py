"""Application-level encryption for secrets at rest.

What is protected, and against which threat
-------------------------------------------
Secrets in this project fall into three groups:

* provider API keys,
* plugin-declared secrets (a plugin's own third-party tokens),
* the JWT signing secret.

None of them may sit in plaintext in SQLite. The realistic threats are mundane and
therefore likely:

* a database file copied to a laptop or synced to cloud storage,
* a backup tarball, a ``git add -A`` of ``data/``,
* an operator pasting a log or a ``.db`` into a bug report,
* the WebUI streaming a config page that accidentally renders raw values.

A Fernet key held **in a separate file outside the database** raises the bar for
all of these: the ciphertext is useless without a second artifact that is not in
the dump. It does not protect against an attacker who has full read access to the
whole host — that is what disk encryption and OS permissions are for, and it is
documented rather than silently assumed.

Why not just ``base64`` (as some bots do)
-----------------------------------------
Base64 is encoding, not encryption. It reads as "encrypted" to a reviewer and
provides zero protection. If a value is stored with ``enc:`` it must actually be
unrecoverable without the key.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
"""Stored-value marker. Makes ciphertext distinguishable from legacy plaintext, so
a migration can find and re-encrypt the remaining rows instead of hoping."""


class SecretBox:
    """Encrypt/decrypt small secrets with a Fernet key.

    The key lives in ``<data_dir>/secret.key`` with ``0600`` permissions and is
    created on first use. ``SOAPBOT_MASTER_KEY`` overrides it (container/KMS
    deployments), which is why the key source is logged at startup — an operator
    who thinks secrets are hardware-backed but is actually using a file key has a
    false sense of security, and that should be visible.
    """

    def __init__(self, key: bytes | str | None = None, *, key_file: Path | None = None) -> None:
        self._key_file = key_file
        if key is None and key_file is not None and key_file.exists():
            key = key_file.read_bytes().strip()
        if key is None:
            key = Fernet.generate_key()
            if key_file is not None:
                self._write_key_file(key_file, key)
            self.source = "generated"
        else:
            self.source = "configured" if not key_file else "file"
        if isinstance(key, str):
            key = key.encode("utf-8")
        try:
            self._fernet = Fernet(key)
        except Exception as exc:  # malformed key: fail fast, never fall back
            raise ValueError(
                "master key is not a valid Fernet key (32 url-safe base64 bytes)"
            ) from exc

    @staticmethod
    def _write_key_file(path: Path, key: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive mode *before* writing, so the key is never
        # briefly world-readable on a permissive umask.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover - Windows / exotic FS
            logger.warning("could not tighten permissions on %s", path)

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            plaintext = ""
        token = self._fernet.encrypt(str(plaintext).encode("utf-8")).decode("ascii")
        return PREFIX + token

    def decrypt(self, stored: str) -> str:
        """Decrypt a stored value; raise on tampering rather than returning junk."""
        if not stored:
            return ""
        if not stored.startswith(PREFIX):
            # Legacy plaintext from before encryption existed. Returned as-is so a
            # migration can read it, but flagged loudly: silently accepting it
            # would mean a "decrypt" path that never actually verified anything.
            logger.warning("read a non-encrypted secret; run the migration")
            return stored
        try:
            return self._fernet.decrypt(stored[len(PREFIX) :].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("secret failed to decrypt (wrong key or tampered)") from exc

    def is_encrypted(self, stored: str) -> bool:
        return bool(stored) and stored.startswith(PREFIX)

    def rewrap(self, stored: str) -> str:
        """Decrypt-and-re-encrypt, to migrate legacy values in place."""
        return self.encrypt(self.decrypt(stored))


_default_box: SecretBox | None = None


def get_secret_box(key_file: Path | None = None) -> SecretBox:
    """Process-wide secret box, created lazily."""
    global _default_box
    if _default_box is None:
        if key_file is None:
            from soapbot.config import settings

            key = settings.master_key or None
            if not key and settings.master_key_file is not None:
                # Read the key from a mounted secret rather than the environment.
                # ``strip()`` matters: a key written by ``openssl rand -base64`` ends
                # in a newline, and a Fernet key with trailing whitespace fails with a
                # message that points at the ciphertext, not the key.
                key = settings.master_key_file.read_text(encoding="utf-8").strip() or None
            key_file = None if key else settings.data_dir / "secret.key"
        else:
            key = None
        _default_box = SecretBox(key, key_file=key_file)
    return _default_box


def reset_secret_box(box: SecretBox | None = None) -> None:
    """Test seam: install a known box, or clear it."""
    global _default_box
    _default_box = box
