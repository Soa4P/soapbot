"""The security claims in SECURITY.md must match the code, including its gaps.

Why this exists
---------------
A security document is most dangerous where it is *slightly* true. "Traces are kept"
reads the same whether the ring holds 500 entries for a process or a database holds six
months of them. The four claims added here have two real gaps (no retention, no token
budget); the point of this file is that turning a gap into a pass fails the suite.

Nothing here starts a service or touches the database: three text assertions, one
source-order assertion, one budget-scope assertion, and one in-memory trace check.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "SECURITY.md"

#: Statements that must survive future edits. Each is a fact about this repository,
#: not a wish: the first two are implemented, the last two are the gaps we refuse to
#: paper over.
REQUIRED_CLAIMS = (
    "提示最终会被提取",
    "不依赖提示保密",
    "输出侧过滤",
    "重启即丢",
    "不可回放",
    "不满足 6 个月保留",
    "没有会话累积上限",
    "committed",
    "reserved",
    "request_id",
    "trace_id",
)

CITED_PATH = re.compile(
    r"`((?:src|docs|scripts)/[A-Za-z0-9_./-]+\.(?:py|md|json|sh|ps1))`"
)


def claims_problems(text: str) -> list[str]:
    """Every missing claim, so a rewrite is reported instead of silently accepted."""
    return [claim for claim in REQUIRED_CLAIMS if claim not in text]


def test_document_states_prompts_can_be_extracted() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    assert "## 提示可被提取的假设" in text
    assert claims_problems(text) == []


def test_document_separates_trace_audit_and_budget() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    assert "## 轨迹、审批记录与成本预算的边界" in text
    # The three locations must be named individually; a merged "audit" section is how
    # "we have traces" quietly becomes "we have six months of evidence".
    assert "src/soapbot/core/trace.py" in text
    assert "src/soapbot/security/audit.py" in text
    assert "src/soapbot/budget/store.py" in text


def test_document_records_the_two_real_gaps() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    assert "**不满足 6 个月保留**" in text
    assert "**模型 token 没有会话累积上限**" in text
    assert "本轮没有做" in text


def test_every_cited_path_exists() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    cited = set(CITED_PATH.findall(text))
    assert cited, "the document cites no repository paths"
    missing = [path for path in sorted(cited) if not (ROOT / path).exists()]
    assert not missing, f"SECURITY.md cites paths that do not exist: {missing}"


def test_integrity_check_precedes_the_origin_branch() -> None:
    """Structural validation must run before the origin decides anything."""
    source = (ROOT / "src" / "soapbot" / "security" / "provenance.py").read_text(
        encoding="utf-8"
    )
    well_formed = source.index("well_formed()")
    data_only = source.index("data_only_origin")
    assert well_formed < data_only, "origin branching now runs before validation"


def test_budget_totals_are_scoped_by_session_and_period() -> None:
    source = (ROOT / "src" / "soapbot" / "budget" / "store.py").read_text(
        encoding="utf-8"
    )
    start = source.index("async def _totals")
    body = source[start : start + 3000]
    assert "session_key" in body
    assert "period" in body
    assert "committed" in body and "reserved" in body


def test_trace_summary_denies_recoverability() -> None:
    from soapbot.core.trace import TraceStore

    summary = TraceStore().summary()
    assert summary["historical"] is False
    assert summary["recoverable"] is False


def test_rewriting_a_gap_as_covered_is_detected() -> None:
    """The reverse case: if the gap sentence changes, the suite must notice."""
    text = SECURITY.read_text(encoding="utf-8")
    tampered = text.replace("**不满足 6 个月保留**", "**已满足 6 个月保留**")
    assert tampered != text
    assert "不满足 6 个月保留" in claims_problems(tampered)

    tampered = text.replace(
        "**模型 token 没有会话累积上限**", "**模型 token 已有会话累积上限**"
    )
    assert "没有会话累积上限" in claims_problems(tampered)
