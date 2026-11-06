#!/usr/bin/env python3
"""Check staged changes or every Git object about to leave the repository."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"),
    re.compile(rb"(?i)\bsk-proj-[A-Za-z0-9_-]{32,}\b"),
    re.compile(rb"(?i)\bAKIA[0-9A-Z]{16}\b"),
)
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".log"}
BLOCKED_BASENAMES = {"id_rsa", "id_ed25519"}
ENV_EXAMPLES = {".env.example", ".env.template", ".env.sample"}


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, input=data, capture_output=True, check=True,
    ).stdout


def check(name: str, content: bytes) -> str | None:
    path = Path(name.lower())
    if path.name in BLOCKED_BASENAMES or path.suffix in BLOCKED_SUFFIXES:
        return "sensitive filename"
    if (path.name.startswith(".env") and path.name not in ENV_EXAMPLES) or (
        "production" in path.name and path.suffix in {".yaml", ".yml", ".json", ".toml"}
    ):
        return "production configuration"
    if b"\0" in content[:8192]:
        return None
    for pattern in PATTERNS:
        for match in pattern.finditer(content):
            if pattern is PATTERNS[3] and match.group() == b"AKIAIOSFODNN7EXAMPLE":
                continue
            return "credential-like content"
    return None


def staged() -> list[tuple[str, bytes]]:
    entries = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split(b"\0")
    result = []
    for raw in filter(None, entries):
        name = raw.decode("utf-8", errors="replace")
        result.append((name, git("show", f":{name}")))
    return result


def outgoing(lines: list[str]) -> list[tuple[str, bytes]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            continue
        _, local, _, remote = fields
        if local == "0" * 40 or not re.fullmatch(r"[0-9a-f]{40,64}", local):
            continue
        if re.fullmatch(r"[0-9a-f]{40,64}", remote) and int(remote, 16):
            commits = git("rev-list", local, f"^{remote}").decode().splitlines()
        else:
            commits = git("rev-list", local, "--not", "--remotes").decode().splitlines()
        for commit in commits:
            tree = git("ls-tree", "-r", "-z", commit)
            for item in filter(None, tree.split(b"\0")):
                meta, raw_name = item.split(b"\t", 1)
                mode, kind, object_id = meta.decode().split()
                if kind != "blob" or mode == "160000":
                    continue
                name = raw_name.decode("utf-8", errors="replace")
                key = (object_id, name)
                if key not in seen:
                    seen.add(key)
                    result.append((name, git("cat-file", "blob", object_id)))
    return result


def committed() -> list[tuple[str, bytes]]:
    result = []
    for item in filter(None, git("ls-tree", "-r", "-z", "HEAD").split(b"\0")):
        meta, raw_name = item.split(b"\t", 1)
        _, kind, object_id = meta.decode().split()
        if kind == "blob":
            result.append((raw_name.decode("utf-8", errors="replace"), git("cat-file", "blob", object_id)))
    return result


def main() -> int:
    try:
        lines = sys.stdin.read().splitlines() if "--pre-push" in sys.argv else []
        if "--pre-push" in sys.argv:
            if not lines:
                print("Push blocked: no pre-push ref data", file=sys.stderr)
                return 1
            items = outgoing(lines)
        elif "--committed" in sys.argv:
            items = committed()
        else:
            items = staged()
        findings = [(name, reason) for name, content in items if (reason := check(name, content))]
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"Secret scan failed closed: {type(exc).__name__}", file=sys.stderr)
        return 1
    for name, reason in findings:
        print(f"Push blocked: {name}: {reason}", file=sys.stderr)
    if findings:
        return 1
    print(f"Secret scan passed: {len(items)} Git objects checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
