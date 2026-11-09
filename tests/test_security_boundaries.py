"""The 20-contract gate must fail when somebody removes an invariant.

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
    # Read the floor from the gate, not from a literal: a literal here would be an
    # eleventh hand-written count, which is the defect the count gate exists to fix.
    for number in range(1, gate.MIN_CONTRACTS + 1):
        assert f"s{number:02d}" in codes, f"contract s{number:02d} has no check"


# ---------------------------------------------------------------- s19 / s20
def test_host_environment_unpacking_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact line the MCP client used to start a server with."""
    _mutate(
        monkeypatch,
        gate.SRC / "mcp" / "client.py",
        "\nenv = {**os.environ, **self.server.env}\n",
    )
    assert "s19" in _codes(False)


def test_the_same_leak_spelled_differently_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``env=os.environ`` and ``env=os.environ.copy()`` are the same defect.

    A gate that only knows the unpacking syntax is defeated by a rename, and the
    rename is what a reviewer under time pressure writes. The three spellings below
    are the ones that actually reach ``create_subprocess_exec``; a copy assigned to a
    local first would need dataflow analysis, which this gate does not pretend to do.
    """
    _mutate(
        monkeypatch,
        gate.SRC / "mcp" / "client.py",
        "\nproc = await asyncio.create_subprocess_exec(cmd, env=os.environ)\n"
        "\nproc = await asyncio.create_subprocess_exec(cmd, env=os.environ.copy())\n"
        "\nproc = await asyncio.create_subprocess_exec(cmd, env=dict(os.environ))\n",
    )
    failed = [r for r in gate.checks() if r.code == "s19" and not r.ok]
    assert failed, "no spelling of the host-environment leak was detected"
    # All three spellings, not just the first one the walk happened to reach.
    assert len(failed[0].evidence.split(";")) >= 3


def test_documenting_the_old_leak_is_not_a_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prose that quotes the defect must not fail the gate.

    ``core/proc_env.py`` explains the bug by quoting the line it replaced. A substring
    gate flags that explanation, so the cheapest way to green is to delete the
    explanation — which is how a security gate teaches people to stop documenting.
    """
    _mutate(
        monkeypatch,
        gate.SRC / "core" / "proc_env.py",
        '\n# It used to pass ``{**os.environ, **server.env}`` to the child.\n',
    )
    assert "s19" not in _codes(False)


def test_a_module_that_stops_sharing_the_table_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A private copy is how the five-copy drift happened the first time.

    The import is *removed*, not shadowed: appending a second assignment would leave
    the gate green, and "the import is still there" is not the property that matters —
    reading the shared object is.
    """
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        if target == gate.SRC / "security" / "principal.py":
            return text.replace("from soapbot.core.text import INVISIBLE", "")
        return text

    monkeypatch.setattr(gate, "_text", fake)
    assert "s20" in _codes(False)


def test_the_isolate_characters_are_required_in_the_shared_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U+2066-U+2069 were the characters every old copy missed."""
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        if target == gate.SRC / "core" / "text.py":
            return text.replace("0x2066", "0x9999")
        return text

    monkeypatch.setattr(gate, "_text", fake)
    assert "s20" in _codes(False)


# ------------------------------------------------- the count cannot drift again
def _rewrite(monkeypatch: pytest.MonkeyPatch, path: Path, old: str, new: str) -> None:
    """Replace ``old`` with ``new`` in one file as the gate sees it."""
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        return text.replace(old, new) if target == path else text

    monkeypatch.setattr(gate, "_text", fake)


def _wire_failures() -> list[Any]:
    return [r for r in gate.checks() if r.code == "wire" and not r.ok]


def test_deleting_a_contract_row_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The silent loss this gate exists for: one row gone, prose untouched.

    Row 12 is removed while the heading still says 20. The old check — "does the
    string `## 20 项防线契约` appear?" — stayed green here, which is precisely why a
    number written in ten places needs a gate that reads it from one place.
    """
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        if target != gate.CONTRACT_DOC:
            return text
        kept = [line for line in text.splitlines() if not line.startswith("| 12 |")]
        return "\n".join(kept)

    monkeypatch.setattr(gate, "_text", fake)
    failures = _wire_failures()
    assert failures, "a deleted contract row left the gate green"
    evidence = " ".join(r.evidence for r in failures)
    assert "row 12 is 13" in evidence or "19 contracts" in evidence


def test_a_heading_that_disagrees_with_the_table_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The table is the truth; the prose is the claim. They must match."""
    _rewrite(monkeypatch, gate.CONTRACT_DOC, "## 20 项防线契约", "## 18 项防线契约")
    failures = _wire_failures()
    assert failures, "the heading was allowed to disagree with the table"
    assert any("20 项防线契约" in r.evidence for r in failures)


def test_a_makefile_help_line_that_disagrees_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every prose location is checked, not just the document.

    The Makefile help line is the one a developer reads before running the gate; if it
    says 18 while the table has 20, the reader learns the wrong number at the moment
    they are paying attention.
    """
    _rewrite(
        monkeypatch,
        gate.MAKEFILE,
        "20 项安全与错误日志边界审计",
        "18 项安全与错误日志边界审计",
    )
    failures = _wire_failures()
    assert failures, "the Makefile help line was allowed to disagree with the table"
    assert any("Makefile" in r.evidence for r in failures)


def test_the_ratchet_floor_is_not_satisfied_by_deleting_and_updating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consistency alone is not enough — the count may not go down.

    Deleting a row *and* updating all nine prose claims would satisfy the consistency
    half of the check. The ratchet is what stops that: a contract is removed only by
    editing ``MIN_CONTRACTS``, which is a visible, reviewable act.
    """
    original = gate._text

    def fake(target: Path) -> str:
        text = original(target)
        if target == gate.CONTRACT_DOC:
            kept = [line for line in text.splitlines() if not line.startswith("| 20 |")]
            text = "\n".join(kept)
        # Keep the prose self-consistent so only the ratchet can catch this.
        return text.replace("20 项", "19 项").replace("The 20 contracts", "The 19 contracts")

    monkeypatch.setattr(gate, "_text", fake)
    failures = _wire_failures()
    assert failures, "deleting a contract and updating the prose slipped past the ratchet"
    assert any("ratchet floor" in r.evidence for r in failures)
