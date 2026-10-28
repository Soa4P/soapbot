"""Wave 6: the process actually runs the bot.

The defect these tests exist for: ``app.py`` built a plugin manager and a FastAPI app,
and nothing else. ``soapbot start`` served a green ``/api/health`` while no pipeline was
constructed and no adapter was ever dialled — the service could not receive a message.
Every module needed to answer one existed; none of them were reachable from the running
process.

So the assertions here are about *wiring*, not about behaviour that other test files
already cover:

* the lifespan builds a runtime, registers the adapters named in configuration, and
  starts them;
* a broken adapter is reported and skipped rather than taking the API down with it;
* the scheduler drives plugin cron and budget expiry instead of merely being
  constructed;
* a fresh install with no configuration still starts (and says why it is idle).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from soapbot.config import settings
from soapbot.core.adapter import AccountInfo, Adapter, AdapterMeta, Capability
from soapbot.core.config_files import ConfigError, load_adapters, load_providers
from soapbot.core.message import MessageReceipt, OutgoingMessage
from soapbot.core.scheduler import RuntimeScheduler


# ------------------------------------------------------------------ fake adapter
class _FakeAdapter(Adapter):
    """Minimal adapter that records lifecycle calls instead of opening a socket."""

    meta = AdapterMeta(name="fake_rt", display_name="Fake", protocol="test")
    capabilities = frozenset({Capability.TEXT})

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True
        self.health.online = True

    async def stop(self) -> None:
        self.stopped = True
        self.health.online = False

    async def get_self(self) -> AccountInfo:
        return AccountInfo(self_id="1", nickname="fake", adapter="fake_rt")

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        return MessageReceipt(ok=True, message_id="m1")


@pytest.fixture
def fake_adapter_kind():
    from soapbot import adapters

    adapters.register("fake_rt", _FakeAdapter)
    yield "fake_rt"


def _write_config(tmp_path: Path, *, adapters: str = "", providers: str = "") -> Path:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "adapters.yaml").write_text(adapters or "adapters: []\n", encoding="utf-8")
    (config_dir / "providers.yaml").write_text(providers or "providers: []\n", encoding="utf-8")
    return config_dir


# ============================================================ config file loading


def test_missing_config_file_is_empty_not_fatal(tmp_path: Path) -> None:
    """A fresh install has no config. It must boot, not crash-loop.

    Refusing to start without a providers file would make the very first run —
    the one where the operator has nothing configured yet — the hardest one.
    """
    assert load_providers(tmp_path / "nope.yaml") == []
    assert load_adapters(tmp_path / "nope.yaml") == []


def test_malformed_yaml_fails_loudly(tmp_path: Path) -> None:
    """A typo must not degrade into 'zero providers, service looks fine'.

    That failure mode is the worst one available: the process is up, the health check
    is green, and every message silently gets no reply.
    """
    path = tmp_path / "providers.yaml"
    path.write_text("providers: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_providers(path)


def test_duplicate_provider_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n"
        "  - {id: a, kind: openai_compat}\n"
        "  - {id: a, kind: openai_compat}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate provider id"):
        load_providers(path)


def test_env_secret_resolution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOAPBOT_TEST_KEY", "sk-from-env")
    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n  - {id: a, kind: openai_compat, api_key: 'env:SOAPBOT_TEST_KEY'}\n",
        encoding="utf-8",
    )
    configs = load_providers(path)
    assert configs[0].api_key == "sk-from-env"


def test_unset_env_secret_is_an_error_not_an_empty_key(tmp_path: Path, monkeypatch) -> None:
    """An empty api_key produces 401s that get blamed on the provider."""
    monkeypatch.delenv("SOAPBOT_TEST_MISSING", raising=False)
    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n  - {id: a, kind: openai_compat, api_key: 'env:SOAPBOT_TEST_MISSING'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unset environment variable"):
        load_providers(path)


def test_adapter_secret_keys_are_resolved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOAPBOT_TEST_TOKEN", "tok-123")
    path = tmp_path / "adapters.yaml"
    path.write_text(
        "adapters:\n"
        "  - kind: onebot11\n"
        "    account_id: '42'\n"
        "    access_token: 'env:SOAPBOT_TEST_TOKEN'\n",
        encoding="utf-8",
    )
    configs = load_adapters(path)
    assert configs[0].options["access_token"] == "tok-123"
    assert configs[0].options["account_id"] == "42"


def test_duplicate_adapter_kind_rejected(tmp_path: Path) -> None:
    """Two entries would silently collide: the runtime keys adapters by kind."""
    path = tmp_path / "adapters.yaml"
    path.write_text(
        "adapters:\n  - {kind: onebot11}\n  - {kind: onebot11}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="duplicate adapter kind"):
        load_adapters(path)


# ================================================================== scheduler


class _StubCron:
    def __init__(self) -> None:
        self.calls = 0

    async def run_due(self, *, now: float | None = None) -> int:
        self.calls += 1
        return 1

    def schedule(self) -> list[dict]:
        return []


class _StubBudget:
    def __init__(self) -> None:
        self.sweeps = 0

    async def sweep_expired(self, *, now: float | None = None) -> int:
        self.sweeps += 1
        return 0


async def test_scheduler_tick_drives_cron_and_budget() -> None:
    """Both periodic duties ran on the same tick, in one pass.

    Constructing a scheduler is not the same as using one; the modules it drives were
    documented as "called by the app" for two waves while no such caller existed.
    """
    cron, budget = _StubCron(), _StubBudget()
    runtime = SimpleNamespace(
        plugins=SimpleNamespace(cron=cron), budget=budget
    )
    scheduler = RuntimeScheduler(runtime, tick_seconds=30.0)

    await scheduler.tick()

    assert cron.calls == 1
    assert budget.sweeps == 1
    assert scheduler.ticks == 1


async def test_scheduler_tick_isolates_failures() -> None:
    """A failing cron sweep must not stop the budget sweep, or vice versa.

    These are unrelated duties that happen to share a clock; letting one exception
    abort the other means a bug in a plugin silently locks quota forever.
    """

    class _Boom:
        async def run_due(self, *, now=None):
            raise RuntimeError("cron exploded")

    class _Ok:
        def __init__(self) -> None:
            self.sweeps = 0

        async def sweep_expired(self, *, now=None):
            self.sweeps += 1
            return 0

    budget = _Ok()
    scheduler = RuntimeScheduler(
        SimpleNamespace(plugins=SimpleNamespace(cron=_Boom()), budget=budget),
        tick_seconds=30.0,
    )

    await scheduler.tick()

    assert budget.sweeps == 1
    assert "cron exploded" in scheduler.last_error


async def test_scheduler_status_reports_jobs_while_running() -> None:
    """``/api/runtime`` needs to show that a tick is scheduled, not just requested."""

    class _NoPlugins(SimpleNamespace):
        plugins = None

    async def _run() -> tuple[dict, dict]:
        scheduler = RuntimeScheduler(_NoPlugins(), tick_seconds=60.0)
        scheduler.start()
        await asyncio.sleep(0)
        while_running = scheduler.status()
        scheduler.shutdown()
        return while_running, scheduler.status()

    running, stopped = await _run()

    assert running["running"] is True
    assert running["tick_seconds"] == 60.0
    assert running["jobs"]  # the tick is actually registered with APScheduler
    assert stopped["running"] is False
    assert stopped["jobs"] == []


# ============================================================= app lifespan


def test_lifespan_builds_runtime_and_starts_configured_adapter(
    tmp_path: Path, monkeypatch, fake_adapter_kind: str
) -> None:
    """The whole point: configuration reaches the runtime, and the runtime starts."""
    from soapbot.app import create_app, get_plugin_manager, get_runtime, get_scheduler

    config_dir = _write_config(
        tmp_path, adapters=f"adapters:\n  - kind: {fake_adapter_kind}\n"
    )
    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", config_dir)

    with TestClient(create_app()) as client:
        runtime = get_runtime()
        assert runtime is not None
        assert fake_adapter_kind in runtime.adapters
        adapter = runtime.adapters[fake_adapter_kind]
        assert adapter.started is True
        assert get_plugin_manager() is runtime.plugins
        assert get_scheduler() is not None and get_scheduler().status()["running"] is True

        body = client.get("/api/runtime").json()
        assert body["running"] is True
        assert body["adapter_count"] == 1
        assert body["adapters"][fake_adapter_kind]["online"] is True
        assert body["scheduler"]["running"] is True
        assert body["startup_errors"] == []

    # Shutdown unwinds in order, and the adapter is told to stop.
    assert adapter.stopped is True


def test_broken_adapter_is_reported_but_service_stays_up(
    tmp_path: Path, monkeypatch
) -> None:
    """One misconfigured adapter must not remove the UI used to fix it.

    ``unknown_adapter`` has no registry entry, so construction raises. The API has to
    survive that and report it, otherwise the operator is left reading a traceback on
    a terminal with no way to inspect the rest of the configuration.
    """
    from soapbot.app import create_app

    config_dir = _write_config(
        tmp_path, adapters="adapters:\n  - kind: not_a_real_adapter\n"
    )
    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", config_dir)

    with TestClient(create_app()) as client:
        body = client.get("/api/runtime").json()
        assert body["adapter_count"] == 0
        assert any("not_a_real_adapter" in e for e in body["startup_errors"])


def test_runtime_off_keeps_http_only_mode(tmp_path: Path, monkeypatch) -> None:
    """The HTTP-only mode has to stay available; it is what the route tests use."""
    from soapbot.app import create_app, get_plugin_manager, get_runtime

    monkeypatch.setattr(settings, "enable_runtime", False)

    with TestClient(create_app()) as client:
        assert get_runtime() is None
        assert get_plugin_manager() is not None
        assert client.get("/api/runtime").status_code == 503


def test_health_stays_green_with_no_adapters(tmp_path: Path, monkeypatch) -> None:
    """Liveness must not depend on configuration.

    A health check that fails when no adapter is configured takes the management UI
    down at exactly the moment it is needed to configure one.
    """
    from soapbot.app import create_app

    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", _write_config(tmp_path))

    with TestClient(create_app()) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        runtime = client.get("/api/runtime").json()
        assert runtime["adapter_count"] == 0
        assert runtime["running"] is True


async def test_cron_runner_survives_a_tick_interval_longer_than_the_expression() -> None:
    """A job must not run once per tick regardless of its expression.

    The scheduling bug this guards against is the reason ``run_due`` cannot simply
    execute everything it finds: with a 30s tick that is 2880 executions a day for a
    ``0 9 * * *`` job.
    """
    from soapbot.plugins.dispatch import PluginCronRunner

    executed: list[float] = []

    async def _record(caller):
        executed.append(time.time())

    job = {
        "expr": "0 9 * * *",
        "name": "morning",
        "plugin": "p",
        "handler": _record,
    }
    ctx = SimpleNamespace(cron_jobs=[job])
    loader = SimpleNamespace(loaded={"p": SimpleNamespace(name="p", context=ctx)})

    runner = PluginCronRunner(loader)

    start = 1_700_000_000.0  # 2023-11-15 06:13:20 UTC
    assert await runner.run_due(now=start) == 0  # scheduled, not fired

    # Twenty ticks over ten minutes: still nowhere near 09:00 in Asia/Shanghai.
    for offset in range(0, 600, 30):
        await runner.run_due(now=start + offset)
    assert executed == []
