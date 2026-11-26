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
    # Both dispatch paths — local plugin tools and external MCP tools — must be
    # downstream of the admission gate. Anchoring on the external call rather than a
    # literal prefix test keeps the assertion true when routing is tightened.
    assert body.index("vet_arguments(") < body.index("_invoke_external(")


# ---------------------------------- paths, amounts and commands (audit S-AIM-05)
def test_a_model_supplied_path_must_stay_relative() -> None:
    """A path from model output is one bad string away from reading the host's files."""
    assert vet_arguments(_args(path="reports/today.html")).allowed
    for bad in (
        "/etc/passwd",
        "../../config/providers.yaml",
        "reports/../../.env",
        "C:/Windows/system32/config/SAM",
        "~/secret.key",
        "a" + chr(0) + "b",
        "x" * 2000,
    ):
        decision = vet_arguments(_args(path=bad))
        assert not decision.allowed, bad
        assert decision.reason == "unsafe_path:path"


def test_a_host_vetted_path_is_accepted() -> None:
    """A tool that genuinely needs an absolute path says so host-side."""
    args = _args(path="/srv/soapbot/data/out.json")
    assert not vet_arguments(args).allowed
    mark_vetted(args, "path")
    assert vet_arguments(args).allowed


def test_amounts_must_be_real_non_negative_numbers() -> None:
    assert vet_arguments(_args(amount_minor=250)).allowed
    for bad in ("100", -1, None, float("nan"), float("inf"), True):
        decision = vet_arguments(_args(amount_minor=bad))
        assert not decision.allowed, bad
        assert decision.reason == "insane_amount:amount_minor"


def test_a_model_supplied_command_is_never_admitted() -> None:
    """No validator makes a model-authored shell string safe — checking harder is a lie.

    Not even an innocuous-looking one: the rule is about who wrote it, not what it says.
    """
    for name in ("command", "cmd", "script", "shell"):
        decision = vet_arguments(_args(**{name: "echo hi"}))
        assert not decision.allowed, name
        assert decision.reason == f"unvetted_command:{name}"


def test_a_host_built_command_can_be_marked_vetted() -> None:
    """The host constructing the argv itself is the only way a command gets through."""
    args = _args(cmd="fmt --check src")
    mark_vetted(args, "cmd")
    assert vet_arguments(args).allowed


def test_operator_supplied_values_skip_the_model_rules() -> None:
    """These checks exist because the *model* wrote the value; configuration is a host fact."""
    for kwargs in (
        {"path": "/etc/hosts"},
        {"amount_minor": -5},
        {"command": "systemctl restart soapbot"},
    ):
        assert vet_arguments(_args(origin=OPERATOR, **kwargs)).allowed
