"""Tool arguments must carry their origin into the action boundary's decision.

An action-level role check answers "may this caller use this tool?". These tests pin
the other half: a model-produced ``url`` is not the same object as an operator-configured
one, log/telemetry data may never become a resource selector, and a tag that was
tampered with is re-validated instead of trusted.
"""

from __future__ import annotations

from pathlib import Path

from soapbot.security.provenance import (
    LOG,
    MODEL,
    OPERATOR,
    TELEMETRY,
    TOOL_RESULT,
    Provenance,
    ToolArguments,
    mark_vetted,
    vet_arguments,
)

ROOT = Path(__file__).resolve().parents[1]


def _args(**kwargs: object) -> ToolArguments:
    values = {k: v for k, v in kwargs.items() if k != "origin"}
    origin = str(kwargs.get("origin", MODEL))
    return ToolArguments(values, provenance=Provenance(origin=origin))


def test_an_untagged_mapping_is_a_host_constructed_call() -> None:
    """Host code (plugin commands, tests, internal callers) has no model output to trace."""
    decision = vet_arguments({"url": "https://api.example.com"})
    assert decision.allowed
    assert decision.reason == "host_constructed"


def test_a_forged_or_malformed_tag_is_revalidated_at_the_boundary() -> None:
    forged = _args(url="https://api.example.com")
    forged.provenance = MODEL  # type: ignore[assignment]
    assert vet_arguments(forged).reason == "forged_provenance"

    unknown = _args(origin="root", url="https://api.example.com")
    assert vet_arguments(unknown).reason == "forged_provenance"


def test_data_only_origins_cannot_select_a_resource() -> None:
    for origin in (LOG, TELEMETRY, TOOL_RESULT):
        args = _args(origin=origin, url="https://api.example.com")
        decision = vet_arguments(args, resource_check=lambda _v: True)
        assert not decision.allowed
        assert decision.reason == "data_only_origin"


def test_model_resource_parameters_require_a_host_check() -> None:
    args = _args(url="https://api.example.com")
    assert not vet_arguments(args).allowed
    assert vet_arguments(args).reason == "unvetted_resource:url"

    passed = vet_arguments(args, resource_check=lambda _v: True)
    assert passed.allowed
    assert passed.reason == "origin=model"


def test_a_rejected_resource_check_is_a_denial() -> None:
    args = _args(endpoint="http://127.0.0.1:6185/admin")
    assert vet_arguments(args, resource_check=lambda _v: False).reason == (
        "unvetted_resource:endpoint"
    )


def test_a_non_string_or_empty_resource_cannot_sneak_through() -> None:
    assert not vet_arguments(
        _args(url=None), resource_check=lambda _v: True
    ).allowed
    assert not vet_arguments(
        _args(host=""), resource_check=lambda _v: True
    ).allowed


def test_mark_vetted_records_a_real_host_check() -> None:
    args = _args(url="https://api.example.com")
    mark_vetted(args, "url")
    # The checker would reject; the host already validated this exact parameter.
    assert vet_arguments(args, resource_check=lambda _v: False).allowed
    assert args.provenance.vetted == frozenset({"url"})
    assert isinstance(args, dict) and args["url"] == "https://api.example.com"


def test_operator_origin_does_not_need_per_call_vetting() -> None:
    args = _args(origin=OPERATOR, url="https://api.example.com")
    assert vet_arguments(args).allowed


def test_the_model_stage_tags_before_it_dispatches() -> None:
    """A refactor that drops the tag would silently return to action-level-only checks."""
    stage = (ROOT / "src" / "soapbot" / "ai" / "stages.py").read_text(encoding="utf-8")
    body = stage[stage.index("async def _run_tools") :]
    body = body[: body.index("def ", 10)] if "def " in body[10:] else body
    assert "ToolArguments(" in body
    assert body.index("ToolArguments(") < body.index("self.tools.invoke(")


def test_the_registry_checks_provenance_before_either_dispatch_path() -> None:
    dispatch = (
        ROOT / "src" / "soapbot" / "plugins" / "dispatch.py"
    ).read_text(encoding="utf-8")
    body = dispatch[dispatch.index("    async def invoke(") :]
    assert "vet_arguments(" in body
    assert body.index("vet_arguments(") < body.index('name.startswith("mcp__")')
