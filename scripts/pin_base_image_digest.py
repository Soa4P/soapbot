#!/usr/bin/env python3
"""Pin the Dockerfile's base image to a digest (audit S-DEP-08).

``FROM python:3.12-slim`` means "whatever the tag points at today". Tags move: a base
image that gains a package, loses a patch or is re-tagged changes what the deployed
container contains, without a single byte of this repository changing. A digest names
exactly one image.

Why a script rather than a hard-coded digest
--------------------------------------------
The digest has to be looked up from the registry, and doing that here keeps the rewrite
mechanical and reviewable — and lets CI or an operator refresh it on purpose instead of
someone pasting a hash they got from a blog post.

Usage::

    python scripts/pin_base_image_digest.py --image python:3.12-slim           # look it up
    python scripts/pin_base_image_digest.py --image python:3.12-slim --write   # rewrite
    python scripts/pin_base_image_digest.py --digest sha256:abcd... --write    # given

Without ``--write`` it prints the ``FROM`` line that would be used. When the registry is
unreachable the script says so and exits 2; ``--digest`` works offline.

Egress: two hosts, both fixed by this file — ``auth.docker.io`` for the token and
``registry-1.docker.io`` for the manifest. The image argument reaches the URL, so it is
validated as ``name:tag`` against a strict pattern first, redirects are refused, and both
URLs are https with a host from that fixed pair. Nothing the caller types can point this
at another host.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "deploy" / "Dockerfile"
DEFAULT_IMAGE = "python:3.12-slim"

#: The only two hosts this script may talk to.
TOKEN_URL = "https://auth.docker.io/token"
REGISTRY_URL = "https://registry-1.docker.io/v2/{repo}/manifests/{tag}"
ALLOWED_HOSTS = frozenset({"auth.docker.io", "registry-1.docker.io"})

#: ``name[:tag]`` where name is one or two path segments of a safe alphabet. Anything
#: else — a scheme, a host, a query — is refused before it reaches a URL.
_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,99}:[A-Za-z0-9._-]{1,64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

_FROM = re.compile(r"^FROM\s+(?P<image>[^\s]+)(?:\s+AS\s+(?P<alias>\S+))?\s*$", re.MULTILINE)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A registry answers directly; a redirect means something is in the middle."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"refusing to follow a redirect to {newurl}")


def _check_url(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_HOSTS:
        raise ValueError(f"refusing non-registry url: {url}")
    if parsed.username or parsed.password:
        raise ValueError("refusing a url with credentials in it")
    return url


def rewrite(text: str, image: str, digest: str) -> tuple[str, int]:
    """Pin every ``FROM`` that uses ``image`` to ``digest``. Returns (text, count).

    A ``FROM`` that already carries a digest is replaced too: re-pinning is the normal
    operation, and refusing it would push people toward editing by hand.
    """
    if not _IMAGE.match(image):
        raise ValueError(f"image must look like name:tag, got {image!r}")
    if not _DIGEST.match(digest):
        raise ValueError("digest must be sha256:<64 lowercase hex>")
    pinned = f"{image}@{digest}"
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        current = match.group("image")
        base = current.split("@", 1)[0]
        if base != image:
            return match.group(0)
        count += 1
        alias = match.group("alias")
        return f"FROM {pinned} AS {alias}" if alias else f"FROM {pinned}"

    return _FROM.sub(replace, text), count


def lookup_digest(image: str, *, timeout: float = 20.0) -> str:
    """Manifest digest for ``image`` (``repo:tag``), via Docker Hub's registry API."""
    if not _IMAGE.match(image):
        raise ValueError(f"image must look like name:tag, got {image!r}")
    repo, _, tag = image.partition(":")
    if not tag:
        raise ValueError("image must include a tag")
    registry_repo = repo if "/" in repo else f"library/{repo}"

    opener = urllib.request.build_opener(_NoRedirect())
    token_url = _check_url(
        f"{TOKEN_URL}?service=registry.docker.io&scope=repository:{registry_repo}:pull"
    )
    with opener.open(token_url, timeout=timeout) as response:
        token = json.load(response)["token"]

    request = urllib.request.Request(
        _check_url(REGISTRY_URL.format(repo=registry_repo, tag=tag)),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": (
                "application/vnd.oci.image.index.v1+json,"
                "application/vnd.docker.distribution.manifest.list.v2+json,"
                "application/vnd.docker.distribution.manifest.v2+json"
            ),
        },
    )
    with opener.open(request, timeout=timeout) as response:
        digest = response.headers.get("Docker-Content-Digest") or ""
    if not _DIGEST.match(digest):
        raise RuntimeError("registry did not return a digest header")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--digest", default="", help="use this digest instead of looking it up")
    parser.add_argument("--write", action="store_true", help="rewrite the Dockerfile")
    parser.add_argument("--dockerfile", type=Path, default=DOCKERFILE)
    args = parser.parse_args(argv)

    digest = args.digest
    if not digest:
        try:
            digest = lookup_digest(args.image)
        except (ValueError, RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"could not look up a digest for {args.image}: {exc}", file=sys.stderr)
            print("  pass --digest sha256:... to pin without the registry", file=sys.stderr)
            return 2

    try:
        text = args.dockerfile.read_text(encoding="utf-8")
        updated, count = rewrite(text, args.image, digest)
    except (OSError, ValueError) as exc:
        print(f"cannot rewrite {args.dockerfile}: {exc}", file=sys.stderr)
        return 1
    if count == 0:
        print(f"no FROM line uses {args.image} in {args.dockerfile}", file=sys.stderr)
        return 1
    if args.write:
        args.dockerfile.write_text(updated, encoding="utf-8")
        print(f"pinned {count} FROM line(s) to {args.image}@{digest}")
    else:
        for line in updated.splitlines():
            if line.startswith("FROM "):
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
