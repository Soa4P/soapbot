#!/usr/bin/env python3
"""Sign (or verify) a plugin index with the offline maintainer key.

Why this is a script and not part of the bot
--------------------------------------------
The bot only ever *verifies*. Signing needs the private key, and the private key must
never reach a machine that runs the service, a CI runner, or either repository — so
this is an operator tool, run by hand on the machine that holds the key.

Usage
-----
Generate a keypair (once, on the offline machine)::

    python scripts/sign_plugin_index.py --generate-key ~/.soapbot/market-index-signing.key

That writes the private key with mode 0600 and prints the public key + ``key_id`` to
paste into ``src/soapbot/plugins/index_signature.py``. **Do not commit the key.**

Sign an index directory after any change to the published JSON::

    python scripts/sign_plugin_index.py --key ~/.soapbot/market-index-signing.key \\
        --index-dir /path/to/soapbot-plugins

Verify what is on disk (what CI does, no private key needed)::

    python scripts/sign_plugin_index.py --verify --index-dir /path/to/soapbot-plugins
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from soapbot.plugins.index_signature import (  # noqa: E402
    COVERED_DOCUMENTS,
    MARKET_KEY_ID,
    MARKET_PUBLIC_KEY_B64,
    SIGNATURE_FILENAME,
    canonical_payload,
    document_digest,
    verify_documents,
)


def _generate(path: Path) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if path.exists():
        print(f"refusing to overwrite an existing key at {path}", file=sys.stderr)
        return 1
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pem)
    with __import__("contextlib").suppress(OSError):
        os.chmod(path, 0o600)
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    print(f"private key written to {path} (mode 0600) — never commit it")
    print(f"MARKET_PUBLIC_KEY_B64 = {base64.b64encode(raw).decode()}")
    print(f"MARKET_KEY_ID         = {hashlib.sha256(raw).hexdigest()[:16]}")
    return 0


def _load_private_key(path: Path):
    from cryptography.hazmat.primitives import serialization

    try:
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read private key at {path}: {exc}") from exc


def _sign(key_path: Path, index_dir: Path) -> int:
    key = _load_private_key(key_path)
    documents = {name: (index_dir / name).read_bytes() for name in COVERED_DOCUMENTS
                 if (index_dir / name).is_file()}
    if "plugins.json" not in documents:
        print(f"no plugins.json in {index_dir}", file=sys.stderr)
        return 1
    covers = {name: document_digest(body) for name, body in documents.items()}
    signature = key.sign(canonical_payload(covers))
    document = {
        "version": 1,
        "algorithm": "ed25519",
        "key_id": MARKET_KEY_ID,
        "covers": {name: covers[name] for name in sorted(covers)},
        "signature": base64.b64encode(signature).decode(),
    }
    target = index_dir / SIGNATURE_FILENAME
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"signed {len(covers)} document(s) -> {target}")
    for name in sorted(covers):
        print(f"  {name}: {covers[name]}")
    return 0


def _verify(index_dir: Path) -> int:
    signature_path = index_dir / SIGNATURE_FILENAME
    if not signature_path.is_file():
        print(f"missing {signature_path}", file=sys.stderr)
        return 1
    documents = {name: (index_dir / name).read_bytes() for name in COVERED_DOCUMENTS
                 if (index_dir / name).is_file()}
    verdict = verify_documents(
        signature_path.read_bytes(), documents,
        public_key_b64=MARKET_PUBLIC_KEY_B64, key_id=MARKET_KEY_ID,
    )
    if not verdict.ok:
        print(f"signature INVALID: {verdict.reason}", file=sys.stderr)
        return 1
    print(f"signature OK (key {verdict.key_id}), covers: {', '.join(verdict.covered)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-key", type=Path, metavar="PATH")
    parser.add_argument("--key", type=Path, metavar="PATH", help="private key (PKCS#8 PEM)")
    parser.add_argument("--index-dir", type=Path, help="directory holding the published JSON")
    parser.add_argument("--verify", action="store_true", help="verify an existing signature")
    args = parser.parse_args(argv)

    if args.generate_key:
        return _generate(args.generate_key)
    if args.index_dir is None:
        parser.error("--index-dir is required unless --generate-key is used")
    if args.verify:
        return _verify(args.index_dir)
    if args.key is None:
        parser.error("--key is required to sign")
    return _sign(args.key, args.index_dir)


if __name__ == "__main__":
    raise SystemExit(main())
