"""Regression tests for the Wave 4 security re-review (2026-10-28).

Each test below corresponds to a defect that was **reproduced** during the review,
not a hypothetical. The reproduction is preserved as the test's premise, so a
future refactor that reintroduces the flaw fails here rather than in production.

Findings and severity (full write-up in ``docs/plugin-security-review.md``):

  R1 HIGH      SSRF: 100.64.0.0/10 not blocked by ``is_private``, exposing the
               Alibaba Cloud metadata service at 100.100.100.200
  R2 HIGH      SSRF: TOCTOU — pre-flight resolve then a second resolve by httpx
  R3 HIGH      SSRF: non-canonical numeric hosts (``127.1``, ``2130706433``, hex)
  R4 HIGH-BUG  ``ctx.send`` rejected every real session key (``a:b:c`` vs storage charset)
  R5 MED       ``load()`` relied on a coincidental name mismatch to stop traversal
  R6 HIGH      audit ``detail`` stored verbatim: tokens published via the audit stream
  R7 MED       manifest text and plugin output accepted HTML/JS (stored XSS surface)
  R8 HIGH      dependencies carried 130 known vulnerabilities in 6 packages
  R9 MED       ``on_notice`` / ``cron`` registrable but never dispatched
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from soapbot.examples import bundled_plugins_dir
from soapbot.plugins.context import CallerContext, PluginContext
from soapbot.plugins.dispatch import PluginCronRunner, dispatch_notice
from soapbot.plugins.loader import PluginLoader, PluginLoadError
from soapbot.plugins.manifest import Capability, ManifestError, parse_manifest
from soapbot.plugins.sandbox import (
    _SESSION_KEY_RE,
    CapabilityDeniedError,
    CapabilityGrant,
    CapabilityGuard,
    SSRFBlockedError,
    _looks_like_ip_literal,
    _pin_url_to_ip,
    assert_url_allowed,
)
from soapbot.security.audit import AuditLog

#: Bundled examples, not ``data/plugins`` — see ``soapbot.examples``.
PLUGIN_SRC = bundled_plugins_dir()


# ============================================================ R1/R2/R3: SSRF


@pytest.mark.parametrize(
    "url",
    [
        # R1: inside 100.64.0.0/10, which ipaddress.is_private does NOT flag.
        "http://100.100.100.200/latest/meta-data/",
        "http://100.64.0.1/",
        "http://100.127.255.254/",
        # R3: non-canonical numeric encodings of loopback.
        "http://2130706433/",
        "http://0x7f.0.0.1/",
        "http://127.1/",
        "http://0177.0.0.1/",
        # R2/R1: IPv4-in-IPv6 wrappers around blocked addresses.
        "http://[::ffff:169.254.169.254]/",
        "http://[::ffff:127.0.0.1]/",
        # Classic targets, kept to catch a regression in the base rules.
        "http://169.254.169.254/",
        "http://127.0.0.1:6185/api/security/audit",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://198.18.0.1/",
    ],
)
def test_review_ssrf_blocked(url: str) -> None:
    """R1/R3: every one of these was reachable before the fix."""
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed(url)


@pytest.mark.parametrize(
    "url",
    ["https://api.example.com/v1/items", "http://example.com/", "https://1.1.1.1/"],
)
def test_review_public_urls_still_allowed(url: str) -> None:
    """The fix must not block ordinary internet access — a guard that rejects
    everything is not a guard, it is an outage."""
    assert_url_allowed(url)


@pytest.mark.parametrize(
    "host",
    ["127.1", "2130706433", "0x7f.0.0.1", "0177.0.0.1", "169.254.169.254"],
)
def test_review_ip_literal_detection(host: str) -> None:
    assert _looks_like_ip_literal(host) is True


@pytest.mark.parametrize(
    "host", ["example.com", "api-1.example.com", "xn--fiqs8s.example", "a.b.c"]
)
def test_review_hostname_not_mistaken_for_ip(host: str) -> None:
    assert _looks_like_ip_literal(host) is False


def test_review_pin_url_preserves_host_and_query() -> None:
    """R2: connecting by IP must not lose the path/query, or the request silently
    targets a different resource than the plugin asked for."""
    from urllib.parse import urlsplit

    pinned = _pin_url_to_ip(urlsplit("https://example.com/a/b?q=1&r=2"), "1.2.3.4")
    assert pinned == "https://1.2.3.4/a/b?q=1&r=2"


def test_review_pin_url_brackets_ipv6() -> None:
    """Without brackets the colons parse as a port separator."""
    from urllib.parse import urlsplit

    pinned = _pin_url_to_ip(urlsplit("https://example.com:8443/x"), "2001:db8::1")
    assert pinned == "https://[2001:db8::1]:8443/x"


async def test_review_dns_rebinding_name_is_blocked() -> None:
    """R2: a name that resolves to a blocked address must be refused at resolve
    time, and the client then connects to the vetted IP (no second lookup)."""
    from soapbot.plugins.sandbox import resolve_and_verify

    for host in ("localhost", "169.254.169.254.nip.io", "127.0.0.1.nip.io"):
        with pytest.raises(SSRFBlockedError):
            await resolve_and_verify(host)


# ==================================================== R4: ctx.send session key


@pytest.mark.parametrize(
    "key",
    [
        "onebot11:group:123456",
        "onebot11:private:20001",
        "qqofficial:group:ABC123",
    ],
)
def test_review_real_session_keys_accepted(key: str) -> None:
    """R4: the previous check reused the *storage* charset, which forbids ':',
    so ``ctx.send`` raised for 100% of real session keys — the capability could
    never work at all."""
    assert _SESSION_KEY_RE.match(key) is not None


@pytest.mark.parametrize(
    "key",
    ["", "onebot11group123", "onebot11:group:", "a:b:c", "onebot11:group:12 34",
     "onebot11:group:../x", "onebot11:group:" + "9" * 100],
)
def test_review_malformed_session_keys_rejected(key: str) -> None:
    assert _SESSION_KEY_RE.match(key) is None


async def test_review_send_refuses_unobserved_session() -> None:
    """The shape check is not the security boundary; the observed-session
    allow-list is. Both must hold."""
    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="demo",
            declared=frozenset({Capability.SEND}),
            approved=frozenset({Capability.SEND}),
        ),
        audit=AuditLog(),
    )
    ctx = PluginContext(plugin="demo", guard=guard)

    async def sender(session_key: str, text: str) -> None:  # pragma: no cover
        raise AssertionError("must not be called")

    ctx._init_runtime_hooks(sender=sender)
    with pytest.raises(PermissionError):
        await ctx.send("hello", session_key="onebot11:group:999999")


async def test_review_send_works_for_observed_session() -> None:
    """Positive control: the whole path must actually work, otherwise the check is
    just a different way of being broken.

    A real :class:`SessionLedger` is installed here because that is what the loader
    does in production. A bare ``PluginContext`` gets a ``NullLedger`` that permits
    nothing — the safe default, since an unbound context must not be able to send
    anywhere (see the isolation review).
    """
    from soapbot.plugins.isolation import SessionLedger

    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="demo",
            declared=frozenset({Capability.SEND}),
            approved=frozenset({Capability.SEND}),
        ),
        audit=AuditLog(),
    )
    ctx = PluginContext(plugin="demo", guard=guard, session_ledger=SessionLedger())
    sent: list[tuple[str, str]] = []

    async def sender(session_key: str, text: str) -> None:
        sent.append((session_key, text))

    ctx._init_runtime_hooks(sender=sender)
    ctx.remember_session("onebot11:group:123456")
    await ctx.send("hello", session_key="onebot11:group:123456")
    assert sent == [("onebot11:group:123456", "hello")]


# ================================================ R5: loader path containment


async def test_review_load_rejects_traversal_name(tmp_path: Path) -> None:
    """R5: a hostile name must be rejected by an *explicit* check, not because the
    manifest happened to disagree with it."""
    root = tmp_path / "plugins"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plugin.yaml").write_text(
        "name: outside\nversion: 1.0.0\nentry: main:P\ntrust: trusted\n"
        "capabilities: [command]\n",
        encoding="utf-8",
    )
    (outside / "main.py").write_text(
        "class P:\n    def setup(self, ctx):\n        raise SystemExit('executed')\n",
        encoding="utf-8",
    )

    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    loader.approve("outside", {"command"})
    loader.approve("../outside", {"command"})

    with pytest.raises(PluginLoadError) as exc:
        await loader.load("../outside")
    assert "invalid plugin name" in str(exc.value)


@pytest.mark.parametrize("name", ["../x", "..", "a/b", "a\\b", "/abs", "NAME", "1abc", ""])
async def test_review_load_rejects_bad_names(tmp_path: Path, name: str) -> None:
    loader = PluginLoader(plugins_dir=tmp_path, audit=AuditLog())
    with pytest.raises(PluginLoadError):
        await loader.load(name)

    assert loader.loaded == {}


# =================================================== R6: audit redaction


@pytest.mark.parametrize(
    "detail,secret",
    [
        (
            "GET https://api.example.com?token=sk-live-abcdefgh12345678 status=200",
            "sk-live-abcdefgh12345678",
        ),
        ("Authorization: Bearer abcdefghijklmnopqrst", "abcdefghijklmnopqrst"),
        ("request failed api_key=AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        ("password=hunter2hunter2", "hunter2hunter2"),
    ],
)
def test_review_audit_detail_is_redacted(detail: str, secret: str) -> None:
    """R6: the audit log is streamed to the WebUI; a token in ``detail`` would be
    published by the component whose job is to record security events."""
    audit = AuditLog()
    audit.record(kind="plugin", action="invoke", outcome="allow", detail=detail)
    stored = audit.recent()[-1]["detail"]
    assert secret not in stored
    assert "REDACTED" in stored


def test_review_audit_keeps_useful_detail() -> None:
    """Redaction must not gut the trail — an unreadable audit log is a failed one."""
    audit = AuditLog()
    audit.record(
        kind="plugin",
        action="cmd:echo",
        outcome="allow",
        detail="plugin=demo requires Role.MEMBER caller is Role.MEMBER",
        plugin="demo",
    )
    stored = audit.recent()[-1]
    assert "plugin=demo" in stored["detail"]
    assert stored["plugin"] == "demo"


def test_review_audit_detail_length_capped() -> None:
    audit = AuditLog()
    audit.record(kind="plugin", action="x", outcome="allow", detail="a" * 5000)
    assert len(audit.recent()[-1]["detail"]) <= 500


# ======================================================= R7: markup / XSS


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "<iframe src=//evil></iframe>",
    ],
)
def test_review_plugin_output_neutralises_html(payload: str) -> None:
    """R7: plugin output is rendered in chat clients and the WebUI."""
    from soapbot.plugins.sandbox import scrub_plugin_output

    out = scrub_plugin_output(payload)
    assert "<" not in out
    assert ">" not in out


@pytest.mark.parametrize(
    "payload",
    ["[x](javascript:alert(1))", "[x](JavaScript:alert(1))", "[x](data:text/html;base64,xx)"],
)
def test_review_plugin_output_defangs_markdown_schemes(payload: str) -> None:
    """HTML escaping alone does not stop Markdown link schemes."""
    from soapbot.plugins.sandbox import scrub_plugin_output

    out = scrub_plugin_output(payload).lower()
    assert "javascript:" not in out
    assert "data:text/html" not in out


@pytest.mark.parametrize(
    "payload",
    [
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "<iframe src=x>",
        "javascript:alert(1)",
    ],
)
def test_review_manifest_text_neutralises_html(payload: str) -> None:
    """A manifest is authored by the plugin supplier *after* review, so its text
    must be inert wherever it is displayed — the admin UI most of all.

    Note ``</script>`` is *also* blocked, but by the pre-existing forbidden-token
    rule on ``/``. That is defence in depth rather than the same check twice: the
    token rule belongs to the path-safety layer and could reasonably be relaxed,
    while ``neutralise_markup`` is what makes the output inert. This test pins the
    second layer so relaxing the first cannot open the XSS surface.
    """
    manifest = parse_manifest(
        {"name": "demo", "version": "1.0.0", "entry": "main:P", "description": payload}
    )
    assert "<" not in manifest.description
    assert "\x00" not in manifest.description


def test_review_normal_text_passes_through_unchanged() -> None:
    """Guard-rail against over-sanitising: ordinary Chinese text must survive."""
    from soapbot.plugins.sandbox import scrub_plugin_output

    assert scrub_plugin_output("今天的天气不错，共 3 条消息。") == "今天的天气不错，共 3 条消息。"
    assert scrub_plugin_output("https://example.com/path?a=1") == "https://example.com/path?a=1"


# ============================================ R8: dependency vulnerabilities


def test_review_no_known_dependency_vulnerabilities() -> None:
    """R8: 130 advisories across 6 packages were found by pip-audit.

    Asserted in-process rather than by shelling out, so it runs in CI without the
    tool installed. A skip is used when pip-audit is absent: a silent pass would
    claim a guarantee we did not check.
    """
    audit_mod = pytest.importorskip(
        "pip_audit", reason="pip-audit not installed; dependency scan not performed"
    )
    assert audit_mod is not None

    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    payload = json.loads(proc.stdout or "{}")
    deps = payload.get("dependencies", payload if isinstance(payload, list) else [])
    vulnerable = [
        (d.get("name"), d.get("version"), [v.get("id") for v in d.get("vulns", [])])
        for d in deps
        if d.get("vulns")
    ]
    assert vulnerable == [], f"known vulnerable dependencies: {vulnerable}"


# ================================================ R9: notice / cron dispatch


async def test_review_notice_hook_is_dispatched(tmp_path: Path) -> None:
    """R9: ``on_notice`` used to register a hook that nothing ever called."""
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)

    plugin_dir = plugins_dir / "notifier"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "name: notifier\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - notice\n  - storage\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "from soapbot.plugins.base import Plugin\n"
        "class P(Plugin):\n"
        "    async def setup(self, ctx):\n"
        "        @ctx.on_notice\n"
        "        async def hook(caller, notice):\n"
        "            ctx.storage.set('last_notice', notice.get('type', ''))\n",
        encoding="utf-8",
    )

    loader = PluginLoader(plugins_dir=plugins_dir, audit=AuditLog())
    # Approve exactly what the manifest declares, so the grant covers both
    # capabilities. Calling approve() with only {"notice"} here would (correctly)
    # deny the storage write and the hook would fail — which is the capability model
    # working, not a dispatch bug.
    loader.approve_from_manifest(
        next(m for m in loader.discover().found if m.name == "notifier")
    )
    loaded = await loader.load("notifier")
    try:
        caller = CallerContext(
            user_id="20001",
            display_name="tester",
            role="member",
            session_key="onebot11:group:123456",
            scene="group",
        )
        await dispatch_notice(
            loader, caller=caller, notice={"type": "increase", "group_id": "123456"}
        )
        assert loaded.context.storage.get("last_notice") == "increase"
    finally:
        await loader.unload("notifier")


async def test_review_cron_job_is_executed_and_audited(tmp_path: Path) -> None:
    """R9: ``cron`` used to register a job that nothing ever ran."""
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)

    plugin_dir = plugins_dir / "ticker"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "name: ticker\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - cron\n  - storage\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "from soapbot.plugins.base import Plugin\n"
        "class P(Plugin):\n"
        "    async def setup(self, ctx):\n"
        "        @ctx.cron('*/5 * * * *', name='tick')\n"
        "        async def tick(caller):\n"
        "            n = ctx.storage.get('ticks', 0)\n"
        "            ctx.storage.set('ticks', n + 1)\n",
        encoding="utf-8",
    )

    audit = AuditLog()
    loader = PluginLoader(plugins_dir=plugins_dir, audit=audit)
    loader.approve_from_manifest(
        next(m for m in loader.discover().found if m.name == "ticker")
    )
    loaded = await loader.load("ticker")
    try:
        runner = PluginCronRunner(loader, audit=audit)

        # First sighting schedules; it must not fire. Otherwise loading a plugin
        # executes every job it registered, and a restart loop becomes an execution
        # loop — a job registered with ``0 9 * * *`` would run at 3am on every deploy.
        assert await runner.run_due(now=1_700_000_000.0) == 0
        assert loaded.context.storage.get("ticks", 0) == 0

        # Five minutes and change later the ``*/5`` expression is due.
        assert await runner.run_due(now=1_700_000_301.0) == 1
        assert loaded.context.storage.get("ticks") == 1
        assert any(
            e["action"] == "cron:tick" and e["outcome"] == "allow"
            for e in audit.recent()
        )

        # The schedule advanced, so the next tick inside the same window is a no-op.
        assert await runner.run_due(now=1_700_000_310.0) == 0
    finally:
        await loader.unload("ticker")


async def test_review_cron_failure_is_audited_not_swallowed(tmp_path: Path) -> None:
    """An unattended job that fails silently is worse than one that fails loudly:
    nobody is watching, so the audit record is the only signal."""
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)

    plugin_dir = plugins_dir / "crasher"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "name: crasher\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - cron\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "from soapbot.plugins.base import Plugin\n"
        "class P(Plugin):\n"
        "    async def setup(self, ctx):\n"
        "        @ctx.cron('*/5 * * * *', name='boom')\n"
        "        async def boom(caller):\n"
        "            raise RuntimeError('db password hunter2')\n",
        encoding="utf-8",
    )

    audit = AuditLog()
    loader = PluginLoader(plugins_dir=plugins_dir, audit=audit)
    loader.approve_from_manifest(
        next(m for m in loader.discover().found if m.name == "crasher")
    )
    await loader.load("crasher")
    try:
        runner = PluginCronRunner(loader, audit=audit)
        await runner.run_due(now=1_700_000_000.0)
        await runner.run_due(now=1_700_000_301.0)
        record = next(e for e in audit.recent() if e["action"] == "cron:boom")
        assert record["outcome"] == "block"
        assert "RuntimeError" in record["detail"]
        # The exception message must not travel with it.
        assert "hunter2" not in record["detail"]
    finally:
        await loader.unload("crasher")


# ============================================ capability model unchanged


async def test_review_approve_replaces_rather_than_merges(tmp_path: Path) -> None:
    """``approve()`` is a replace, not a union.

    This caught a real mistake while writing the notice test: calling
    ``approve_from_manifest`` and then ``approve(name, {"notice"})`` silently
    *reduced* the grant. Replace semantics are the right choice (the operator is
    stating the full set they want), but the surprise is worth pinning so a future
    refactor to union semantics is a deliberate decision rather than an accident.
    """
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)
    loader = PluginLoader(plugins_dir=plugins_dir, audit=AuditLog())

    manifest = next(m for m in loader.discover().found if m.name == "echo")
    loader.approve_from_manifest(manifest)
    assert Capability.TOOL in loader.grant_for(manifest).effective

    loader.approve("echo", {"command"})
    grant = loader.grant_for(manifest)
    assert Capability.COMMAND in grant.effective
    assert Capability.TOOL not in grant.effective


def test_review_capabilities_still_two_gated() -> None:
    """Guard-rail: the re-review must not have loosened the capability model."""
    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="demo",
            declared=frozenset({Capability.COMMAND}),
            approved=frozenset({Capability.COMMAND}),
        ),
        audit=AuditLog(),
    )
    guard.check(Capability.COMMAND)
    with pytest.raises(CapabilityDeniedError):
        guard.check(Capability.HTTP)


def test_review_manifest_still_rejects_unknown_capability() -> None:
    with pytest.raises(ManifestError):
        parse_manifest(
            {"name": "demo", "version": "1.0.0", "entry": "main:P", "capabilities": ["nope"]}
        )
