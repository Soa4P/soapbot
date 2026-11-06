"""Regression tests for the local and CI push gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "scripts" / "check_secrets.py"
_spec = importlib.util.spec_from_file_location("check_secrets", _MODULE)
assert _spec and _spec.loader
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)


def test_sensitive_paths_and_credentials_are_blocked() -> None:
    assert scanner.check(".env.production", b"x=y")
    assert scanner.check("logs/runtime.log", b"ready")
    assert scanner.check("data/user.sqlite", b"binary")
    assert scanner.check("private.pem", b"file")
    assert scanner.check("src/app.py", b"-----BEGIN " + b"PRIVATE KEY-----\n")
    assert scanner.check("src/app.py", b"AKIA" + b"A" * 16)


def test_placeholders_and_exact_mock_are_not_secrets() -> None:
    assert scanner.check(".env.example", b"SOAPBOT_API_KEY=replace-me") is None
    assert scanner.check("tests/mock.py", b"AKIAIOSFODNN7EXAMPLE") is None
    assert scanner.check("src/app.py", b"api_key='put-your-secret-here'") is None
    assert scanner.check("tests/mock.py", b"AKIA" + b"B" * 16)
