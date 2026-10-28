"""Plugin/host isolation tests (2026-10-28 isolation review).

Every test here corresponds to an attack that was **executed successfully** against
the codebase before the fix. They are regression locks, not hypotheticals.

Scope note — read this before trusting the suite
------------------------------------------------
These tests prove the *encapsulation* layer holds and that the process boundary
contains crash/hang/memory bombs. They do **not** prove a plugin cannot touch the
filesystem or network: an in-process plugin with the bot's OS privileges can always
do that, and pretending otherwise is the failure mode this project explicitly
refuses. See ``docs/plugin-isolation.md`` for the layer-by-layer guarantee and the
deployment requirements that close the rest.

Findings (severity from the review):

  I1 HIGH  ``ctx._guard.grant = <all caps>`` — self-escalation by attribute write
  I2 HIGH  ``ctx._storage_backend["other"]["token"]`` — cross-plugin secret read
  I3 HIGH  ``ctx._observed_sessions.add(<any group>)`` — broadcast to any group
  I4 HIGH  no process boundary: ``os._exit`` / monkeypatch killed or blinded the host
  I5 MED   plugin API trusted the bind address for its localhost-only guarantee
  I6 LOW   ``_fts_index`` interpolated a caller-supplied table name into SQL
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.plugins.context import PluginContext
from soapbot.plugins.isolation import (
    HOST_AUTHORITY,
    IsolatedRunner,
    IsolationError,
    NullLedger,
    PluginCrashedError,
    PluginTimeoutError,
    SessionLedger,
)
from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import (
    CapabilityDeniedError,
    CapabilityGrant,
    CapabilityGuard,
    EncryptedPluginStorage,
    PluginStorage,
)
from soapbot.security.audit import AuditLog


def _guard(caps: set[Capability], plugin: str = "p") -> CapabilityGuard:
    return CapabilityGuard(
        CapabilityGrant(plugin=plugin, declared=frozenset(caps), approved=frozenset(caps)),
        audit=AuditLog(),
    )


# ============================================ I1: self-escalation via ctx attributes


def test_i1_cannot_reassign_guard() -> None:
    """``ctx._guard.grant = ...`` was a working self-escalation."""
    ctx = PluginContext(plugin="evil", guard=_guard({Capability.COMMAND}))
    with pytest.raises(AttributeError):
        ctx._guard.grant = CapabilityGrant(
            plugin="evil",
            declared=frozenset(Capability),
            approved=frozenset(Capability),
        )


def test_i1_cannot_mutate_grant_fields() -> None:
    """The grant is a frozen dataclass; its fields cannot be rewritten either."""
    guard = _guard({Capability.COMMAND})
    with pytest.raises(FrozenInstanceError):
        guard.grant.approved = frozenset(Capability)


def test_i1_cannot_unseal_guard() -> None:
    """``_sealed`` gates the write check, so it must itself be unwritable."""
    guard = _guard({Capability.COMMAND})
    with pytest.raises(AttributeError):
        guard._sealed = False
    # And the denial still holds afterwards.
    with pytest.raises(AttributeError):
        guard.grant = None


def test_i1_escalation_attempt_leaves_grants_intact() -> None:
    """A failed escalation must not partially succeed."""
    guard = _guard({Capability.COMMAND})
    before = guard.grant.effective
    with pytest.raises(AttributeError):
        guard.grant = CapabilityGrant(plugin="evil", approved=frozenset(Capability))
    assert guard.grant.effective == before
    with pytest.raises(CapabilityDeniedError):
        guard.check(Capability.HTTP)


# ============================================ I2: cross-plugin storage isolation


def test_i2_context_holds_only_own_namespace() -> None:
    """``ctx._storage_backend`` must never contain another plugin's namespace."""
    backend: dict = {}
    a = PluginContext(plugin="plugin_a", guard=_guard({Capability.STORAGE}), storage_backend=backend)
    b = PluginContext(plugin="plugin_b", guard=_guard({Capability.STORAGE}), storage_backend=backend)
    a.storage.set("api_token", "sk-live-A")

    assert "plugin_a" not in b._storage_backend
    with pytest.raises(KeyError):
        _ = b._storage_backend["plugin_a"]["api_token"]


def test_i2_storage_view_cannot_reach_outer_mapping() -> None:
    """The bound view holds a slice, so indexing by plugin name yields nothing."""
    backend: dict = {}
    a = PluginStorage("plugin_a", backend)
    b = PluginStorage("plugin_b", backend)
    a.set("token", "A-secret")

    assert "plugin_a" not in b._backend
    assert b.get("token") is None


def test_i2_encrypted_storage_also_scoped() -> None:
    """The encrypted variant inherits the same scoping; check it explicitly."""
    backend: dict = {}

    class _Box:
        def encrypt(self, s: str) -> str:
            return "enc:v1:" + s[::-1]

        def decrypt(self, s: str) -> str:
            return s[len("enc:v1:") :][::-1]

    a = EncryptedPluginStorage("plugin_a", backend, _Box())
    b = EncryptedPluginStorage("plugin_b", backend, _Box())
    a.set("token", "A-secret")

    assert "plugin_a" not in b._backend
    assert b.get("token") is None


def test_i2_normal_namespacing_still_works() -> None:
    """Positive control: isolation must not break ordinary per-plugin storage."""
    backend: dict = {}
    a = PluginStorage("plugin_a", backend)
    b = PluginStorage("plugin_b", backend)
    a.set("token", "A")
    b.set("token", "B")
    assert (a.get("token"), b.get("token")) == ("A", "B")
    assert a.keys() == ["token"]
    assert a.all() == {"token": "A"}


# ============================================ I3: send-target injection


async def test_i3_context_has_no_observed_sessions_attribute() -> None:
    """The writable set is gone; plugins cannot find it to add a target."""
    ctx = PluginContext(plugin="evil", guard=_guard({Capability.SEND}))
    assert not hasattr(ctx, "_observed_sessions")


async def test_i3_ledger_write_requires_host_authority() -> None:
    ledger = SessionLedger()
    with pytest.raises(PermissionError):
        ledger.record("evil", "onebot11:group:999999999")
    assert ledger.permits("evil", "onebot11:group:999999999") is False


async def test_i3_cannot_send_to_unobserved_group() -> None:
    """End-to-end: the plugin tries to message a group it was never invoked for."""
    sent: list[tuple[str, str]] = []

    async def sender(k: str, t: str) -> None:
        sent.append((k, t))

    ctx = PluginContext(
        plugin="evil", guard=_guard({Capability.SEND}), session_ledger=SessionLedger()
    )
    ctx._init_runtime_hooks(sender=sender)

    with pytest.raises(PermissionError):
        await ctx.send("spam", session_key="onebot11:group:999999999")
    assert sent == []


async def test_i3_null_ledger_permits_nothing() -> None:
    """An unbound context must fail closed, not default to open."""
    ledger = NullLedger()
    assert ledger.permits("anyone", "onebot11:group:1") is False
    ledger.record("anyone", "onebot11:group:1")  # no-op, must not raise
    assert ledger.permits("anyone", "onebot11:group:1") is False


async def test_i3_host_grant_then_send_works() -> None:
    """Positive control: the host recording a session makes sending possible."""
    sent: list[tuple[str, str]] = []

    async def sender(k: str, t: str) -> None:
        sent.append((k, t))

    ledger = SessionLedger()
    ctx = PluginContext(plugin="demo", guard=_guard({Capability.SEND}), session_ledger=ledger)
    ctx._init_runtime_hooks(sender=sender)

    ctx.remember_session("onebot11:group:123456")  # host hook, holds authority
    await ctx.send("hello", session_key="onebot11:group:123456")
    assert sent == [("onebot11:group:123456", "hello")]


async def test_i3_grants_revoked_on_unload(tmp_path: Path) -> None:
    """A reload must start with an empty allow-list.

    Otherwise a plugin could earn a grant, be replaced with different code under the
    same name, and inherit the previous version's reach.
    """
    import shutil

    from soapbot.plugins.loader import PluginLoader

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    from soapbot.examples import bundled_plugins_dir

    shutil.copytree(bundled_plugins_dir() / "echo", plugins_dir / "echo")

    loader = PluginLoader(plugins_dir=plugins_dir, audit=AuditLog())
    manifest = next(m for m in loader.discover().found if m.name == "echo")
    loader.approve_from_manifest(manifest)
    await loader.load("echo")

    loader.session_ledger.record("echo", "onebot11:group:1", authority=HOST_AUTHORITY)
    assert loader.session_ledger.permits("echo", "onebot11:group:1")

    await loader.unload("echo")
    assert not loader.session_ledger.permits("echo", "onebot11:group:1")


# ============================================ I4: process boundary


def _write_plugin(dir_: Path, source: str) -> Path:
    (dir_ / "main.py").write_text(source, encoding="utf-8")
    return dir_


async def _run(source: str, *, timeout: float = 3.0):
    tmp = Path(tempfile.mkdtemp())
    _write_plugin(tmp, source)
    runner = IsolatedRunner(timeout=timeout, memory_bytes=256 * 1024 * 1024)
    return await runner.run_entry(
        plugin_dir=tmp,
        attr="Plugin",
        handler="handler",
        payload={"caller": {"user_id": "1"}, "args": ["x"]},
    )


async def test_i4_normal_plugin_returns_result() -> None:
    out = await _run(
        "class Plugin:\n    def handler(self, caller, args):\n        return 'ok:' + args[0]\n"
    )
    assert out == "ok:x"


async def test_i4_os_exit_does_not_kill_host() -> None:
    """Before the process boundary, ``os._exit(0)`` ended the bot."""
    with pytest.raises(PluginCrashedError):
        await _run(
            "import os\nclass Plugin:\n    def handler(self, caller, args):\n        os._exit(0)\n"
        )
    # If the host died, this line would never run.
    assert True


async def test_i4_sigkill_of_parent_fails_without_harm() -> None:
    """A plugin that tries to kill the host process must fail harmlessly.

    '' is used as the signal-free probe: the child raises (no permission / not
    supported) and reports the error type. The point is that the *host* survives.
    """
    with pytest.raises((PluginCrashedError, IsolationError)):
        await _run(
            "import os, signal\n"
            "class Plugin:\n"
            "    def handler(self, caller, args):\n"
            "        os.kill(os.getppid(), signal.SIGKILL)\n"
            "        return 'sent'\n"
        )
    assert True


async def test_i4_infinite_loop_times_out() -> None:
    started = time.perf_counter()
    with pytest.raises(PluginTimeoutError):
        await _run(
            "import time\n"
            "class Plugin:\n"
            "    def handler(self, caller, args):\n"
            "        while True: time.sleep(0.05)\n",
            timeout=1.5,
        )
    elapsed = time.perf_counter() - started
    # The deadline is enforced by the parent, so it holds even though the child
    # never cooperates.
    assert elapsed < 6.0


async def test_i4_exception_message_does_not_cross_boundary() -> None:
    """Only the exception *type* crosses; the message (often a token) does not."""
    with pytest.raises(PluginCrashedError) as exc:
        await _run(
            "class Plugin:\n"
            "    def handler(self, caller, args):\n"
            "        raise RuntimeError('token=sk-live-SHOULD-NOT-LEAK')\n"
        )
    assert "SHOULD-NOT-LEAK" not in str(exc.value)
    assert "RuntimeError" in str(exc.value)


async def test_i4_non_serialisable_result_rejected() -> None:
    """The child cannot hand the parent a live object to revive."""
    with pytest.raises(PluginCrashedError):
        await _run(
            "class Plugin:\n"
            "    def handler(self, caller, args):\n"
            "        return object()\n"
        )


async def test_i4_child_cannot_import_host_package() -> None:
    """The child runs with ``-I`` and no PYTHONPATH, so ``import soapbot`` fails.

    This matters because the host package exposes the audit log and the runtime:
    if the child could import it, 'isolated' would be a word rather than a boundary.
    """
    with pytest.raises(PluginCrashedError):
        await _run(
            "import soapbot\n"
            "class Plugin:\n"
            "    def handler(self, caller, args):\n"
            "        return 'imported'\n"
        )


# ============================================ I5: plugin API localhost enforcement


def _fake_request(host: str, *, headers: dict[str, str] | None = None, method: str = "GET"):
    from types import SimpleNamespace

    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers=headers or {},
        method=method,
        url=SimpleNamespace(path="/api/plugins"),
        state=SimpleNamespace(),
    )


def test_i5_plugin_api_rejects_anonymous_non_loopback_client() -> None:
    """The guarantee must be code, not a bind-address assumption.

    A remote client with no token is refused. The status is 401 rather than the old
    404: the UI has to be able to tell "you need to log in" apart from "this endpoint
    does not exist", and only one of those is actionable.
    """
    from fastapi import HTTPException

    from soapbot.api.plugins import _authorize

    with pytest.raises(HTTPException) as exc:
        _authorize(_fake_request("203.0.113.7"))
    assert exc.value.status_code == 401
    assert exc.value.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "testclient"])
def test_i5_loopback_clients_allowed(host: str) -> None:
    from soapbot.api.plugins import _authorize

    _authorize(_fake_request(host))


def test_i5_loopback_cannot_be_driven_cross_site() -> None:
    """A page on another origin must not be able to POST to the loopback API.

    A plain HTML form submission is not subject to a CORS preflight, so the request
    arrives from loopback with whatever credentials the browser has. Checking Origin
    on state-changing requests is what closes that.
    """
    from fastapi import HTTPException

    from soapbot.api.plugins import _authorize

    with pytest.raises(HTTPException) as exc:
        _authorize(
            _fake_request(
                "127.0.0.1",
                headers={"Origin": "https://evil.example"},
                method="POST",
            )
        )
    assert exc.value.status_code == 403


def test_i5_loopback_get_is_not_origin_checked() -> None:
    """Read-only cross-origin GETs stay allowed: they leak nothing a token protects."""
    from soapbot.api.plugins import _authorize

    _authorize(_fake_request("127.0.0.1", headers={"Origin": "https://other.example"}))


def test_i5_plugin_endpoints_require_loopback_via_testclient() -> None:
    """TestClient presents as 'testclient', which is allowed; sanity-check wiring."""
    from soapbot.app import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/plugins").status_code in (200, 503)


# ============================================ I6: SQL identifier allow-list


async def test_i6_fts_index_rejects_unknown_table() -> None:
    """``table`` is interpolated into SQL, so it must be allow-listed."""
    from soapbot.memory.store import _fts_index

    class _Session:
        async def begin_nested(self):  # pragma: no cover - must not be reached
            raise AssertionError("must validate before touching the session")

    with pytest.raises(ValueError, match="unknown FTS table"):
        await _fts_index(_Session(), "memories_fts; DROP TABLE memories;--", "x", 1)


def test_i6_known_fts_tables_pass_validation() -> None:
    """Guard-rail: the allow-list must actually contain the real tables."""
    from soapbot.memory.store import _FTS_TABLES

    assert {"messages_fts", "memories_fts", "knowledge_fts"} <= _FTS_TABLES


# ============================================ capability model intact


def test_capability_two_gate_model_unchanged() -> None:
    """The isolation work must not have loosened the two-gate model."""
    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="p",
            declared=frozenset({Capability.COMMAND}),
            approved=frozenset({Capability.COMMAND, Capability.HTTP}),
        ),
        audit=AuditLog(),
    )
    guard.check(Capability.COMMAND)
    with pytest.raises(CapabilityDeniedError):
        guard.check(Capability.HTTP)  # approved but not declared
