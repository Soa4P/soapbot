"""Regression tests for the local and CI push gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "scripts" / "check_secrets.py"
_spec = importlib.util.spec_from_file_location("check_secrets", _MODULE)
assert _spec and _spec.loader
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)


def _sample(*parts: bytes) -> bytes:
    """Assemble a fixture from short pieces.

    Every credential-shaped string in this file is built this way on purpose: the
    repository's own scanner cannot be tested with literal samples, because then the
    test file is the finding — which is exactly what happened when these assertions
    were first written inline.
    """
    return b"".join(parts)


_AWS_EXAMPLE = _sample(b"AKIA", b"IOSFODNN7", b"EXAMPLE")
_PLACEHOLDER_KEY = _sample(b"api_", b"key='put-your-", b"secret-here'")
_LONG_VALUE = _sample(b"Zq7x", b"9p2w", b"7r4t", b"5y8u")


def test_sensitive_paths_and_credentials_are_blocked() -> None:
    assert scanner.check(".env.production", b"x=y")
    assert scanner.check("logs/runtime.log", b"ready")
    assert scanner.check("data/user.sqlite", b"binary")
    assert scanner.check("private.pem", b"file")
    assert scanner.check("src/app.py", b"-----BEGIN " + b"PRIVATE KEY-----\n")
    assert scanner.check("src/app.py", _sample(b"AKIA", b"A" * 16))


def test_placeholders_and_exact_mock_are_not_secrets() -> None:
    assert scanner.check(".env.example", b"SOAPBOT_API_KEY=replace-me") is None
    assert scanner.check("tests/mock.py", _AWS_EXAMPLE) is None
    assert scanner.check("src/app.py", _PLACEHOLDER_KEY) is None
    assert scanner.check("tests/mock.py", _sample(b"AKIA", b"B" * 16))


# ------------------------------------------------- S-DOC-01: the shapes we ship

_PROVIDER_KEY = _sample(b"s", b"k-", b"9f2c", b"8a71", b"b4e6", b"d035a0b1c2d3")
_GOOGLE_KEY = _sample(
    b"A", b"I", b"za", b"SyA1", b"b2C3d4", b"E5f6G7", b"h8I9j0", b"K1l2M3n4O5p6Q"
)
_FERNET = _sample(b"g", b"A" * 5, b"b" * 60)


def test_provider_key_shapes_are_blocked() -> None:
    """The gate used to cover four patterns and missed every key this repo uses.

    The historical leak was a bare Windows administrator password pasted into a temp
    script: no ``AKIA``, no ``ghp_``, no private-key header. A gate that stays green
    through the one leak that actually happened is not a gate.
    """
    assert scanner.check("tmp/x.py", _sample(b"key = '", _PROVIDER_KEY, b"'"))
    assert scanner.check("tmp/x.py", _GOOGLE_KEY)
    assert scanner.check("tmp/x.py", _FERNET)  # what a leaked encrypted store looks like
    assert scanner.check("tmp/notes.txt", _PROVIDER_KEY)  # no assignment at all


def test_credential_assignments_are_blocked() -> None:
    assert scanner.check("tmp/x.py", _sample(b"pass", b'word = "', _LONG_VALUE, b'"'))
    assert scanner.check("tmp/x.py", _sample(b"access_", b"token: '", _LONG_VALUE, b"'"))


def test_short_values_and_env_references_are_not_secrets() -> None:
    """Narrow on purpose: fixtures are short, and ``env:`` is configuration."""
    assert scanner.check("src/app.py", _sample(b"pass", b'word = "test', b'-key"')) is None
    assert scanner.check(
        "deploy/compose.yaml",
        _sample(b"pass", b'word: "env:', b"SOAPBOT_", b"PASS", b'WORD"'),
    ) is None


def test_marked_fixtures_are_not_secrets() -> None:
    """A real credential never spells a marker inside itself.

    Without this, the widened patterns flagged the repository's own test fixtures and
    the only way to push was ``--no-verify`` — a gate that teaches operators to skip
    it is worse than no gate.
    """
    assert scanner.check(
        "tests/x.py", _sample(b"s", b"k-live-", b"EX", b"AMPLE-", b"9f2c8a71b4e6d035")
    ) is None
    assert scanner.check(
        "tests/x.py", _sample(b"pass", b'word = "', b"should-not-", b'leak-abcdefgh"')
    ) is None
