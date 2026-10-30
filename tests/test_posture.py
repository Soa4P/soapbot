"""Deployment posture checks — and the gate logic that makes them worth anything.

The bug these tests were written against
----------------------------------------
``PostureReport.ok`` counted only ``Status.FAIL``. ``check_secrets_in_env`` returned
``WARN`` at ``HIGH`` severity. The two sets did not intersect, so a host with
``SOAPBOT_MASTER_KEY`` exported in its environment printed ``verdict: PASS`` and
exited 0 under ``--strict``.

That is the worst shape a security check can fail in: the control exists, reports
honestly, and is ignored. So the tests below assert on the *verdict*, not just on the
finding, and there is one test per previously-invisible combination.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from soapbot.security.posture import (
    Finding,
    PostureReport,
    Severity,
    Status,
    check_bind_address,
    check_config_dir_writable,
    check_key_file_mode,
    check_provider_config,
    check_secrets_in_env,
    probe_providers,
    run_posture_checks,
)

#: Substrings the detector treats as secret-bearing, mirrored here so the tests can
#: clear the environment the same way the check reads it.
_SECRET_MARKERS = ("SECRET", "PASSWORD", "PASSWD", "TOKEN", "API_KEY", "APIKEY", "MASTER_KEY")


@pytest.fixture(autouse=True)
def _empty_secret_environment(monkeypatch):
    """Run every test in this module against a known-empty secret environment.

    ``check_secrets_in_env`` reads the *whole* ``os.environ``, and assertions here are
    exact (a PASS verdict, a count of 12). A CI runner exports its own variables, and
    some match the detector — ``ACTIONS_RUNTIME_TOKEN`` is the one that bit: four of
    these tests went red on Windows for a reason unrelated to the code under test.

    Stripping first keeps the assertion about the detector instead of about whoever
    launched pytest. It does not weaken the check: the variables each test needs are
    set by the test itself, and no test asserts on ambient state.
    """
    for key in list(os.environ):
        if any(marker in key.upper() for marker in _SECRET_MARKERS):
            monkeypatch.delenv(key, raising=False)
    yield


# ------------------------------------------------------------------ gate logic


def _f(status: Status, severity: Severity, check: str = "x") -> Finding:
    return Finding(check=check, status=status, severity=severity, detail="")


@pytest.mark.parametrize("severity", [Severity.CRITICAL, Severity.HIGH])
def test_high_severity_warn_fails_the_gate(severity):
    """The regression: HIGH + WARN used to pass, and that combination is meaningful.

    "This is serious, and it is currently wrong" must not be reported as healthy.
    """
    report = PostureReport(findings=[_f(Status.WARN, severity)])
    assert report.ok is False


@pytest.mark.parametrize("severity", [Severity.CRITICAL, Severity.HIGH])
def test_high_severity_fail_fails_the_gate(severity):
    assert PostureReport(findings=[_f(Status.FAIL, severity)]).ok is False


@pytest.mark.parametrize("severity", [Severity.MEDIUM, Severity.LOW])
def test_medium_warn_still_passes(severity):
    """A writable plugin dir in a container is normal; failing on it trains people
    to pass ``--ignore-strict``, which is worse than not having a gate."""
    assert PostureReport(findings=[_f(Status.WARN, severity)]).ok is True


def test_unknown_does_not_fail():
    """UNKNOWN means "could not check here" (Windows uid model, no container).

    Failing on it would make the gate impossible to satisfy on developer machines
    and CI runners, and the check still prints so the gap is visible.
    """
    assert PostureReport(findings=[_f(Status.UNKNOWN, Severity.CRITICAL)]).ok is True


def test_pass_does_not_fail():
    assert PostureReport(findings=[_f(Status.PASS, Severity.CRITICAL)]).ok is True


def test_empty_report_is_ok():
    """Vacuously true, but it is the state before checks run and must not crash."""
    assert PostureReport().ok is True


# ----------------------------------------------------------- secrets in the env


def test_secrets_in_env_is_a_failure_not_a_warning(monkeypatch):
    monkeypatch.setenv("SOAPBOT_MASTER_KEY", "ZmFrZQ==")
    finding = check_secrets_in_env()
    assert finding.status is Status.FAIL, "a readable master key must fail the gate"
    assert finding.severity is Severity.HIGH
    assert "SOAPBOT_MASTER_KEY" in finding.detail
    assert finding.remediation


@pytest.mark.parametrize(
    "name",
    [
        "SOAPBOT_JWT_SECRET",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "DB_PASSWORD",
        "PGPASSWD",
        "TLS_PRIVATE_KEY",
    ],
)
def test_secret_markers_cover_real_world_names(monkeypatch, name):
    """Substring markers, because the set of provider variables is unbounded."""
    monkeypatch.setenv(name, "x")
    assert check_secrets_in_env().status is Status.FAIL


@pytest.mark.parametrize(
    "name",
    ["SOAPBOT_MASTER_KEY_FILE", "SOAPBOT_JWT_SECRET_FILE", "DB_PASSWORD_PATH"],
)
def test_file_pointer_variables_are_not_secrets(monkeypatch, name):
    """A *_FILE variable holds a path, not a secret.

    The bug this covers was self-defeating: the remediation text for this very check
    says "use SOAPBOT_MASTER_KEY_FILE", yet setting it was counted as one more leaked
    secret at HIGH severity — so following the advice failed the gate and told the
    operator to follow it. Anyone hitting that loop concludes the gate is broken and
    stops reading it.
    """
    monkeypatch.setenv(name, "/run/secrets/master_key")
    assert check_secrets_in_env().status is Status.PASS


def test_clean_environment_passes(monkeypatch):
    # Strip anything secret-looking the developer's shell may hold. ``monkeypatch``
    # restores it afterwards: deleting straight from ``os.environ`` leaks into every
    # later test in the same process, which can make an unrelated secrets test pass
    # for the wrong reason.
    for k in list(os.environ):
        if any(
            m in k.upper()
            for m in ("SECRET", "PASSWORD", "PASSWD", "TOKEN", "API_KEY", "APIKEY", "MASTER_KEY")
        ):
            monkeypatch.delenv(k, raising=False)
    assert check_secrets_in_env().status is Status.PASS


def test_secret_names_are_truncated_in_output(monkeypatch):
    """A finding lands in CI logs; printing 50 names verbatim is noise, and the count
    plus a sample is what an operator needs."""
    for i in range(12):
        monkeypatch.setenv(f"CI_API_KEY_{i}", "x")
    detail = check_secrets_in_env().detail
    assert detail.endswith("...")
    assert detail.startswith("12 ")


# ------------------------------------------------------------------ bind address


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_bind_passes(host):
    assert check_bind_address(host).status is Status.PASS


@pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])
def test_wildcard_bind_is_critical(host):
    """The control API manages plugins and capabilities; a public bind is an
    unauthenticated admin surface."""
    finding = check_bind_address(host)
    assert finding.status is Status.FAIL
    assert finding.severity is Severity.CRITICAL
    assert PostureReport(findings=[finding]).ok is False


def test_a_wildcard_bind_inside_a_container_warns_instead_of_failing():
    """In a container, 0.0.0.0 is how a published port reaches the process at all.

    Reporting CRITICAL there made `doctor --strict` fail on deploy/docker-compose.yml —
    the reference deployment of this very repository. A gate that is red on its own
    hardened topology teaches people to pass `--strict` with their eyes closed. What is
    actually knowable from inside is nothing: the exposure is the host's port mapping.
    """
    finding = check_bind_address("0.0.0.0", in_container=True)
    assert finding.status is Status.WARN
    assert finding.severity is Severity.MEDIUM
    assert "docker port" in (finding.remediation or "")
    # MEDIUM must not trip the gate — that is the whole point of the downgrade.
    assert PostureReport(findings=[finding]).ok is True


def test_specific_external_address_is_only_a_warning():
    """Binding one routable address may be deliberate (behind a proxy), so it warns
    rather than fails — but at MEDIUM, which does not block the gate."""
    finding = check_bind_address("10.0.0.5")
    assert finding.status is Status.WARN
    assert finding.severity is Severity.MEDIUM


def test_unspecified_bind_is_unknown_not_pass():
    """Silence is not evidence of safety."""
    assert check_bind_address(None).status is Status.UNKNOWN


# ---------------------------------------------------------------- key file mode


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes; Windows uses ACLs")
def test_world_readable_key_file_fails(tmp_path: Path):
    key = tmp_path / "secret.key"
    key.write_text("ZmFrZQ==", encoding="utf-8")
    key.chmod(0o644)
    finding = check_key_file_mode(key)
    assert finding.status is Status.FAIL
    assert "chmod 600" in finding.remediation


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes; Windows uses ACLs")
def test_private_key_file_passes(tmp_path: Path):
    key = tmp_path / "secret.key"
    key.write_text("ZmFrZQ==", encoding="utf-8")
    key.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert check_key_file_mode(key).status is Status.PASS


def test_missing_key_file_is_unknown_not_pass():
    """The key may legitimately come from elsewhere; claiming PASS would overstate."""
    assert check_key_file_mode(Path("/nonexistent/secret.key")).status is Status.UNKNOWN


# ------------------------------------------------------------- full report shape


def test_report_serialises_and_summarises(tmp_path: Path):
    report = run_posture_checks(
        plugin_manager=None,
        plugin_dir=tmp_path,
        key_path=None,
        data_dir=tmp_path,
        bind_host="127.0.0.1",
    )
    payload = [f.to_dict() for f in report.findings]
    assert payload and all({"check", "status", "severity", "detail"} <= set(d) for d in payload)
    total = sum(report.summary().values())
    assert total == len(report.findings)


def test_isolation_check_is_present_and_critical(tmp_path: Path):
    """The whole deployment story rests on this one; it must be CRITICAL so that a
    deployment with isolation off cannot pass the gate."""
    report = run_posture_checks(
        plugin_manager=None,
        plugin_dir=tmp_path,
        key_path=None,
        data_dir=tmp_path,
        bind_host="127.0.0.1",
    )
    iso = next(f for f in report.findings if f.check == "isolation.process")
    assert iso.severity is Severity.CRITICAL
    # With no manager supplied the honest answer is UNKNOWN, not PASS.
    assert iso.status is Status.UNKNOWN


# ------------------------------------------------------- upstream provider wiring
#
# Before this check existed, `providers: []` produced no finding at all: `doctor`
# printed a clean sheet for a bot that could not answer a single message, and a config
# pointed at a local mock was indistinguishable from one pointed at a real vendor.


def _providers_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "providers.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _one_provider(base_url: str) -> str:
    return (
        "providers:\n"
        "  - id: primary\n"
        "    kind: openai_compat\n"
        f"    base_url: {base_url}\n"
        "    model: deepseek-chat\n"
    )


def test_an_empty_provider_list_is_reported_not_ignored(tmp_path: Path):
    finding = check_provider_config(_providers_file(tmp_path, "providers: []\n"))
    assert finding.status is Status.WARN
    assert finding.severity is Severity.MEDIUM
    assert "空" in finding.detail
    assert finding.remediation


def test_a_missing_providers_file_is_a_warning(tmp_path: Path):
    finding = check_provider_config(tmp_path / "absent.yaml")
    assert finding.status is Status.WARN


def test_unparseable_yaml_fails_at_high_severity(tmp_path: Path):
    """Always a real problem, unlike an empty list — and it also means the process
    will refuse to start, so the gate should catch it here first."""
    finding = check_provider_config(_providers_file(tmp_path, "providers: [\n"))
    assert finding.status is Status.FAIL
    assert finding.severity is Severity.HIGH


def test_a_loopback_endpoint_is_named_as_not_cloud(tmp_path: Path):
    finding = check_provider_config(
        _providers_file(tmp_path, _one_provider("http://127.0.0.1:11434/v1"))
    )
    assert finding.status is Status.WARN
    assert "primary" in finding.detail
    assert "不是真实云端" in finding.detail


def test_plain_http_to_a_remote_host_is_flagged(tmp_path: Path):
    finding = check_provider_config(
        _providers_file(tmp_path, _one_provider("http://api.example.com/v1"))
    )
    assert finding.status is Status.WARN
    assert "http://" in finding.detail


def test_a_remote_https_provider_passes(tmp_path: Path):
    finding = check_provider_config(
        _providers_file(tmp_path, _one_provider("https://api.deepseek.com/v1"))
    )
    assert finding.status is Status.PASS
    assert "1" in finding.detail


def test_the_provider_check_reaches_the_report(tmp_path: Path):
    report = run_posture_checks(
        plugin_manager=None,
        plugin_dir=tmp_path,
        key_path=None,
        data_dir=tmp_path,
        bind_host="127.0.0.1",
        providers_file=_providers_file(tmp_path, "providers: []\n"),
    )
    finding = next(f for f in report.findings if f.check == "provider.upstream")
    assert finding.status is Status.WARN
    # MEDIUM must not trip the deploy gate: a host that only runs the panel is a
    # legitimate deployment, and a red gate on a fresh install is a gate people disable.
    assert finding.severity is Severity.MEDIUM


async def test_a_rejection_counts_as_reachable(tmp_path: Path) -> None:
    """The rule: "did something answer", not "was the key accepted".

    Through a mock transport rather than a socket, because on a host that intercepts
    loopback HTTP (CI containers, some corporate images) the request comes back as an
    infrastructure error and the rule under test never runs at all. The socket is the
    next test's job.
    """
    import httpx

    def factory(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(401))
        return httpx.AsyncClient(transport=transport, **kwargs)

    path = _providers_file(tmp_path, _one_provider("https://api.example.com/v1"))
    results = await probe_providers(path, timeout=3.0, client_factory=factory)

    assert results[0]["reachable"] is True
    assert results[0]["status_code"] == 401

    def broken(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        return httpx.AsyncClient(transport=transport, **kwargs)

    down = await probe_providers(path, timeout=3.0, client_factory=broken)
    # 5xx means the far side is the one that is ill, and that is a finding, not a pass.
    assert down[0]["reachable"] is False


async def test_probe_against_a_real_listening_endpoint(tmp_path: Path):
    """The same rule over a real socket — when the host lets one through.

    A throwaway HTTP server stands in for the vendor and answers 401. It also asserts
    that the probe sends no credential: 401 is a *pass*, and that is only true because
    nothing sensitive was on the wire.
    """
    import contextlib
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            self.send_response(401)
            self.end_headers()

        def log_message(self, *args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        path = _providers_file(tmp_path, _one_provider(f"http://127.0.0.1:{port}/v1"))
        results = await probe_providers(path, timeout=3.0)
    finally:
        with contextlib.suppress(Exception):
            server.shutdown()
        server.server_close()

    assert len(results) == 1
    if results[0]["status_code"] != 401:
        # Something between this process and loopback answered instead of the server.
        # That is a property of the host, not of the probe; the rule is covered above.
        pytest.skip(f"loopback HTTP is intercepted here (HTTP {results[0]['status_code']})")
    assert results[0]["reachable"] is True
    assert results[0]["local"] is True
    # No credential was sent, so nothing in the result can leak one.
    assert "api_key" not in results[0]


# --------------------------------------------------- the config directory is writable
#
# The symptom this check exists for: the panel answers "saved", the process restarts, and
# the configuration is unchanged — because the directory is read-only or is not the one
# the next boot reads. Naming the path is what makes that a five-second diagnosis.


def test_a_writable_config_dir_passes_and_names_its_files(tmp_path: Path):
    (tmp_path / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    finding = check_config_dir_writable(tmp_path)
    assert finding.status is Status.PASS
    assert finding.severity is Severity.MEDIUM
    assert "providers.yaml" in finding.detail


def test_an_empty_but_writable_dir_passes_and_says_it_will_be_seeded(tmp_path: Path):
    finding = check_config_dir_writable(tmp_path)
    assert finding.status is Status.PASS
    assert "播种" in finding.detail


def test_a_missing_config_dir_is_a_warning(tmp_path: Path):
    finding = check_config_dir_writable(tmp_path / "absent")
    assert finding.status is Status.WARN
    assert finding.severity is Severity.MEDIUM
    assert finding.remediation


def test_a_read_only_config_dir_explains_the_save_that_does_not_stick(
    tmp_path: Path, monkeypatch
):
    """``os.access`` is patched because a POSIX chmod is meaningless on Windows, and
    this check has to behave the same on both — it is the operator's diagnosis, not a
    platform quirk they should have to know about."""
    import soapbot.security.posture as posture

    monkeypatch.setattr(posture.os, "access", lambda path, mode: False)
    finding = check_config_dir_writable(tmp_path)
    assert finding.status is Status.WARN
    # The explanation is the feature: "saved" and "in effect" are different claims.
    assert "重启后不会生效" in finding.detail
    assert "只读" in finding.detail
    # MEDIUM must not fail the deploy gate: editing files over SSH is a valid choice.
    assert PostureReport(findings=[finding]).ok is True


def test_an_unspecified_config_dir_is_unknown_not_pass():
    assert check_config_dir_writable(None).status is Status.UNKNOWN


def test_the_config_directory_check_reaches_the_report(tmp_path: Path):
    report = run_posture_checks(
        plugin_manager=None,
        plugin_dir=tmp_path,
        key_path=None,
        data_dir=tmp_path,
        bind_host="127.0.0.1",
        config_dir=tmp_path,
    )
    finding = next(f for f in report.findings if f.check == "config.writable")
    assert finding.status is Status.PASS
