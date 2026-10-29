"""The README's own acceptance rule, enforced by a test.

``README.md`` says, above the capability matrix: "如实标注，避免『文档说有、实际没有』"
(labelled truthfully, so the document never claims something the code does not do).

That rule was violated four times in a row and nobody noticed, because a claim in prose
has no failing build. This module turns two of the claims into assertions:

* every ``SOAPBOT_*`` variable the README documents must exist in ``Settings`` —
  a documented knob that the code ignores is worse than an undocumented one, since an
  operator will set it and wait for an effect;
* every ``Settings`` field must be either documented or explicitly listed as internal,
  so a new setting cannot ship without the operator being able to find it.

The matrix itself is not parsed: prose cells are not a reliable machine format, and a
test that greps for "✅" would pass on a wrong row. What can be checked mechanically is
checked; what cannot is reviewed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from soapbot.config import Settings

README = Path(__file__).resolve().parent.parent / "README.md"

#: Settings that are deliberately undocumented in the operator table.
#:
#: Each entry is a decision, not an oversight. Anything added here should say why it is
#: not an operator knob.
_INTERNAL = {
    "db_url": "derived from data_dir; overriding it is an escape hatch, not a setting",
    "config_dir": "documented separately under 配置文件, not the env table",
    "data_dir": "documented separately under 配置文件",
    "host": "documented in the table under its unprefixed name (HOST)",
    "port": "documented in the table under its unprefixed name (PORT)",
    "master_key": "documented as MASTER_KEY / MASTER_KEY_FILE",
    "master_key_file": "documented as MASTER_KEY / MASTER_KEY_FILE",
    "jwt_secret": "internal: rotated automatically, never operator-chosen",
    "jwt_ttl_hours": "internal default",
    "init_token": "internal: printed at startup and written to data/init_token.txt",
    "first_run_owner": "internal bookkeeping for the first login",
    "trust_protocol_roles": "internal: only meaningful for the QQ official adapter",
    "log_ring_size": "internal default for the in-memory log buffer",
    "default_timezone": "internal default, overridden per persona",
    "budget_currency": "advanced budget tuning, documented in docs/ not the table",
    "budget_period": "advanced budget tuning",
    "budget_period_cap_minor": "advanced budget tuning",
    "budget_per_request_cap_minor": "advanced budget tuning",
    "budget_request_ttl_seconds": "advanced budget tuning",
    "bilibili_tier": "advanced bilibili tuning",
    "bilibili_timeout_seconds": "advanced bilibili tuning",
    "bilibili_min_interval_seconds": "advanced bilibili tuning",
    "bilibili_rate_per_minute": "advanced bilibili tuning",
    "bilibili_max_comments": "advanced bilibili tuning",
    "stream_chunk_chars": "advanced streaming tuning",
    "stream_first_packet_deadline": "advanced streaming tuning",
    "stream_send_interval": "advanced streaming tuning",
    "user_blacklist": "documented separately in 安全默认值",
    "scheduler_tick_seconds": "internal default",
}


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _documented_env_names() -> set[str]:
    """``SOAPBOT_``-prefixed names, plus the unprefixed aliases the table also lists.

    The table writes ``HOST`` rather than ``SOAPBOT_HOST`` because the prefix is stated
    once in the heading — so both forms count as documented.
    """
    text = _readme_text()
    names = {m.lower() for m in re.findall(r"`(?:SOAPBOT_)?([A-Z][A-Z0-9_]*)`", text)}
    return {n for n in names if n}


def _prefixed_documented() -> set[str]:
    """Names written explicitly as ``SOAPBOT_FOO``."""
    return {m.lower() for m in re.findall(r"`SOAPBOT_([A-Z][A-Z0-9_]*)`", _readme_text())}


def _table_row_names() -> set[str]:
    """Variable names from the **first column** of the environment-variable table.

    Only the first cell counts. An earlier version scanned the whole row and picked up
    default values like ``INFO`` and ``PROGRESSIVE`` as if they were variable names —
    the test then failed for the wrong reason, which is how a guard earns a reputation
    for being unreliable and gets deleted.
    """
    text = _readme_text()
    start = text.find("### 环境变量")
    assert start != -1, "the environment-variable section was renamed or removed"
    end = text.find("## ", start + 10)
    section = text[start : end if end != -1 else len(text)]
    names: set[str] = set()
    for row in section.splitlines():
        if not row.startswith("|"):
            continue
        cells = row.split("|")
        if len(cells) < 3:
            continue
        first = cells[1]
        for name in re.findall(r"`(?:SOAPBOT_)?([A-Z][A-Z0-9_]*)`", first):
            names.add(name.lower())
    return names


def test_every_documented_variable_exists_in_settings() -> None:
    """A documented knob the code ignores is a lie with a UI.

    Catches the reverse of the usual drift too: a variable removed from ``Settings``
    while its row stayed in the README.
    """
    known = {name.lower() for name in Settings.model_fields}
    documented = _table_row_names()

    unknown = sorted(documented - known)
    assert not unknown, (
        "README documents variables the code does not define: "
        f"{unknown}. Either add them to Settings or remove the row."
    )


def test_every_settings_field_is_documented_or_declared_internal() -> None:
    """A setting nobody can find is a setting nobody will use.

    The ``_INTERNAL`` list is the escape hatch, and every entry carries a reason — this
    test exists so that adding a field forces exactly one of two decisions.
    """
    documented = _documented_env_names() | _table_row_names()
    missing = [
        name
        for name in Settings.model_fields
        if name.lower() not in documented and name.lower() not in _INTERNAL
    ]
    assert not missing, (
        "Settings fields neither documented in the README nor declared internal: "
        f"{missing}. Add a row, or add it to _INTERNAL with a reason."
    )


def test_internal_list_has_no_stale_entries() -> None:
    """An exemption for a field that no longer exists hides the next one."""
    known = {name.lower() for name in Settings.model_fields}
    stale = sorted(name for name in _INTERNAL if name not in known)
    assert not stale, f"_INTERNAL lists fields that no longer exist: {stale}"


def test_every_internal_entry_explains_itself() -> None:
    for name, reason in _INTERNAL.items():
        assert reason.strip(), f"_INTERNAL[{name!r}] needs a reason"


@pytest.mark.parametrize(
    "variable",
    [
        # The one this round added. It is the difference between voice working and
        # silently degrading on the most common single-machine deployment, so it must
        # stay discoverable.
        "voice_allow_hosts",
        "voice_enabled",
        "voice_tts_enabled",
        "stream_reply",
    ],
)
def test_header_level_knobs_stay_documented(variable: str) -> None:
    """Pinned individually: these are the ones whose absence causes silent no-ops."""
    assert variable in _table_row_names(), (
        f"{variable} is missing from the README environment table; "
        "an operator cannot turn the feature on without it"
    )
