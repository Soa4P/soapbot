"""The 18-contract gate must fail when somebody removes an invariant.

A static gate that only ever prints green is decoration. These tests mutate the
source *in memory* — no file is touched — and assert the corresponding check flips
to a failure. That is the whole contract: the gate is allowed to be wrong about a
detail, but it is not allowed to be blind to the primitive it was written to ban.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "check_security_boundaries.py"

_spec = importlib.util.spec_from_file_location("check_security_boundaries", GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
# dataclasses resolves cls.__module__ through sys.modules; without this line the
# dynamically loaded module's @dataclass raises AttributeError at import time.
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)


def _mutate(monkeypatch: pytest.MonkeyPatch, path: Path, suffix: str) -> None:
    """Append ``suffix`` to one file as seen by the gate, without writing to disk."""
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        return text + suffix if target == path else text

    monkeypatch.setattr(gate, "_text", fake)


def _codes(ok: bool) -> set[str]:
    return {r.code for r in gate.checks() if r.ok is ok}


def test_shell_true_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.SRC / "mcp" / "client.py", "\nsubprocess.run(cmd, shell=True)\n")
    assert "s02" in _codes(False)


def test_pickle_loads_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.APP, "\nimport pickle\nx = pickle.loads(b'')\n")
    failed = [r for r in gate.checks() if not r.ok]
    assert any(r.code == "s03" for r in failed)


def test_unsafe_yaml_load_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.SRC / "plugins" / "loader.py", "\ny = yaml.load(raw)\n")
    assert "s03" in _codes(False)


def test_wildcard_cors_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.APP, '\napp.add_middleware(CORSMiddleware, allow_origins=["*"])\n')
    assert "s06" in _codes(False)


def test_a_second_v_html_binding_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    target = gate.WEBUI / "components" / "ProtocolEnd.vue"
    _mutate(monkeypatch, target, '\n<div v-html="serverBody"></div>\n')
    assert "s04" in _codes(False)


def test_local_storage_token_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.CLIENT, "\nlocalStorage.setItem('soapbot.token', t)\n")
    assert "s05" in _codes(False)


def test_raw_exception_detail_is_not_allowed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.ADMIN, "\nraise HTTPException(422, detail=str(exc))\n")
    assert "s11" in _codes(False)


def test_a_silent_except_body_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    _mutate(monkeypatch, gate.APP, "\ntry:\n    pass\nexcept Exception:\n    pass\n")
    assert "s13" in _codes(False)


def test_provider_response_body_in_error_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    target = gate.SRC / "providers" / "openai_compat.py"
    _mutate(monkeypatch, target, "\nerr = resp.text[:400]\n")
    assert "s14" in _codes(False)


def test_gate_exits_non_zero_when_a_contract_is_missing(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    _mutate(monkeypatch, gate.APP, "\nimport pickle\n")
    assert gate.main() == 1
    assert "missing" in capsys.readouterr().out


def test_every_numbered_contract_has_at_least_one_check() -> None:
    codes = {r.code for r in gate.checks()}
    for number in range(1, 19):
        assert f"s{number:02d}" in codes, f"contract s{number:02d} has no check"
