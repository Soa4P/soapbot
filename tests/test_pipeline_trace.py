"""Trace collection and the topology contract.

The most valuable test in this file is ``test_stage_order_matches_build_pipeline``.
Everything else checks that the ring stores what it was given; that one checks the
thing a reviewer cannot: whether the graph the panel draws still describes the
pipeline that actually runs. Drift there is silent — the panel keeps rendering a
correct-looking 20-stage path while the runtime has 21, and the extra one is invisible
exactly when someone is trying to find where a message stopped.
"""

from __future__ import annotations

import pytest

from soapbot.core.trace import (
    ORDER_CONSTRAINTS,
    STAGE_ORDER,
    TraceStore,
    build_topology,
    violated_constraints,
)

# ------------------------------------------------------------------ context stub


class _Event:
    def __init__(self, trace_id: str, session_key: str = "onebot11:group:1") -> None:
        self.trace_id = trace_id
        self.session_key = session_key


class _Stage:
    """Minimal stand-in for ``Stage``; the store only reads ``.name``."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Ctx:
    def __init__(
        self,
        stages: list[tuple[str, float]],
        *,
        halted: bool = False,
        reason: str = "",
        trace_id: str = "t-1",
        extras: dict | None = None,
    ) -> None:
        self.event = _Event(trace_id)
        self.timings = dict(stages)
        self.halted = halted
        self.halt_reason = reason
        self.started_at = 0.0
        self.extras = extras or {}


def _feed(store: TraceStore, ctx: _Ctx) -> None:
    for name, ms in (ctx.timings or {}).items():
        store.observe_stage(ctx, _Stage(name), ms)
    store.on_processed(ctx)


# ------------------------------------------------------------------- ingestion


def test_one_trace_is_stored_with_all_stages() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("dedup", 0.5), ("guard", 1.2), ("model", 900.0)]))

    traces = store.recent()
    assert len(traces) == 1
    assert [s.name for s in traces[0].stages] == ["dedup", "guard", "model"]
    assert traces[0].total_ms == pytest.approx(901.7)


def test_stages_are_ordered_even_if_observed_out_of_order() -> None:
    """The pipeline runs in order, but a trace assembled from a dict is not guaranteed to be."""
    store = TraceStore()
    ctx = _Ctx([("model", 10.0), ("dedup", 1.0)])
    for name, ms in [("model", 10.0), ("dedup", 1.0)]:
        store.observe_stage(ctx, _Stage(name), ms)
    store.on_processed(ctx)

    assert [s.name for s in store.recent()[0].stages] == ["dedup", "model"]


def test_slowest_stage_is_reported() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("dedup", 1.0), ("model", 800.0), ("reply", 5.0)]))
    slowest = store.recent()[0].slowest()
    assert slowest == {"name": "model", "elapsed_ms": 800.0}


def test_halted_trace_keeps_its_reason() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("guard", 2.0)], halted=True, reason="whitelist"))
    trace = store.recent()[0]
    assert trace.halted is True
    assert trace.halt_reason == "whitelist"
    assert store.counters["halted"] == 1
    assert store.counters["handled"] == 0


def test_context_with_no_stages_is_still_recorded() -> None:
    """A message that halted before the first stage is the case worth seeing."""
    store = TraceStore()
    store.on_processed(_Ctx([], halted=True, reason="dedup"))
    assert len(store.recent()) == 1


def test_non_scalar_extras_are_dropped() -> None:
    """A large object in extras would pin memory for the life of the ring."""
    store = TraceStore()
    _feed(
        store,
        _Ctx(
            [("dedup", 1.0)],
            extras={"provider": "primary", "payload": {"big": "x" * 5000}, "tokens": 42},
        ),
    )
    extras = store.recent()[0].extras
    assert extras == {"provider": "primary", "tokens": 42}


def test_ring_is_bounded_and_drops_the_oldest() -> None:
    store = TraceStore(capacity=3)
    for i in range(5):
        _feed(store, _Ctx([("dedup", float(i))], trace_id=f"t-{i}"))
    ids = [t.trace_id for t in store.recent()]
    assert ids == ["t-4", "t-3", "t-2"]


def test_recent_returns_newest_first() -> None:
    store = TraceStore()
    for i in range(3):
        _feed(store, _Ctx([("dedup", 1.0)], trace_id=f"t-{i}"))
    assert [t.trace_id for t in store.recent()] == ["t-2", "t-1", "t-0"]


def test_lookup_by_trace_id() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("dedup", 1.0)], trace_id="abc"))
    assert store.by_trace("abc") is not None
    assert store.by_trace("missing") is None


def test_failure_counter_is_separate_from_halt() -> None:
    """A crashed pipeline and a refused message are different events."""
    store = TraceStore()
    store.note_failure()
    assert store.counters["failed"] == 1
    assert store.counters["halted"] == 0


# --------------------------------------------------------------------- metrics


def test_metrics_sample_after_first_trace() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("dedup", 10.0)]))
    samples = store.metrics()
    assert samples, "第一条 trace 之后应当立刻产生一个采样点"
    assert samples[-1].handled == 1


def test_percentile_returns_an_observed_value() -> None:
    """Nearest-rank, so p95 is a duration that actually occurred."""
    store = TraceStore()
    for ms in [10.0, 20.0, 30.0, 40.0, 1000.0]:
        _feed(store, _Ctx([("dedup", ms)], trace_id=f"t{ms}"))
    summary = store.summary()
    assert summary["p95_ms"] in {10.0, 20.0, 30.0, 40.0, 1000.0}
    assert summary["max_ms"] == 1000.0


def test_summary_declares_it_is_not_historical() -> None:
    """So a client cannot render an empty panel as '0 ms, all good'."""
    store = TraceStore()
    summary = store.summary()
    assert summary["historical"] is False
    assert "重启即清空" in summary["note"]


def test_clear_resets_everything() -> None:
    store = TraceStore()
    _feed(store, _Ctx([("dedup", 5.0)]))
    store.clear()
    assert store.recent() == []
    assert store.metrics() == []
    assert store.counters == {"handled": 0, "halted": 0, "failed": 0}


# -------------------------------------------------------------------- topology


def test_topology_lists_every_stage_in_order() -> None:
    topology = build_topology()
    assert [s["name"] for s in topology["stages"]] == list(STAGE_ORDER)
    assert topology["reorderable"] is False


def test_topology_has_labels_for_every_stage() -> None:
    for stage in build_topology()["stages"]:
        assert stage["label"] and stage["label"] != stage["name"], f"{stage['name']} 没有中文标签"


def test_stage_order_matches_build_pipeline() -> None:
    """The contract this module cannot derive and must not guess.

    ``build_pipeline`` is the single source of truth for stage order. ``STAGE_ORDER``
    is a copy kept for the graph. If they drift, the panel draws a pipeline that does
    not exist — and does it convincingly.
    """
    import inspect
    import re

    from soapbot.core import builder as builder_module
    from soapbot.plugins import dispatch as dispatch_module

    source = inspect.getsource(builder_module.build_pipeline)
    # Read the stage class names out of the assembly function. Ordering is the point,
    # so `findall` on the add() calls in source order is exactly right.
    added = re.findall(r"pipeline\.add\(\s*([A-Za-z_][\w]*)\s*\(", source)
    assert added, "未能从 build_pipeline 中读出任何 pipeline.add() 调用"

    def resolve(class_name: str):
        # Plugin stages live in `plugins.dispatch` and are imported lazily inside the
        # function, so they are not attributes of the builder module. Looking only at
        # the builder silently skipped exactly the two stages most likely to be added
        # or renamed without the graph being updated.
        return getattr(builder_module, class_name, None) or getattr(
            dispatch_module, class_name, None
        )

    resolved: list[str] = []
    unresolved: list[str] = []
    for class_name in added:
        cls = resolve(class_name)
        name = getattr(cls, "name", None) if cls else None
        if isinstance(name, str):
            resolved.append(name)
        else:
            unresolved.append(class_name)

    assert not unresolved, f"这些 Stage 类找不到 .name，检查需要扩展：{unresolved}"

    # Every stage the builder adds must appear in STAGE_ORDER. The reverse is not
    # asserted: STAGE_ORDER may contain conditional stages (plugin hooks, memory write)
    # that this particular assembly omitted.
    missing = [n for n in resolved if n not in STAGE_ORDER]
    assert not missing, f"STAGE_ORDER 缺少 build_pipeline 实际装配的 Stage：{missing}"


def test_constraints_reference_known_stages() -> None:
    """Every constraint must name real stages and say *why* in whole sentences.

    The reason now comes from the catalogue, so this also proves the key exists in both
    languages: a missing key would resolve to the key string itself, which is longer
    than eight characters and would otherwise sail through a length check.
    """
    from soapbot.core.trace import constraint_reason

    for before, after in ORDER_CONSTRAINTS:
        assert before in STAGE_ORDER, f"约束引用了未知 Stage {before}"
        assert after in STAGE_ORDER, f"约束引用了未知 Stage {after}"
        for locale in ("zh-CN", "en-US"):
            reason = constraint_reason(before, after, locale)
            assert reason != f"pipeline.constraint.{before}.{after}", (
                f"{before}->{after} 在 {locale} 缺少译文"
            )
            assert len(reason) > 8, f"{before}->{after} 的理由太短，等于没说"


def test_topology_labels_are_translated_not_echoed() -> None:
    """A missing label key would come back as the key, and the graph would show
    `pipeline.stage.model` — legible to nobody, and easy to miss in a screenshot."""
    for locale, expected in (("zh-CN", "模型调用"), ("en-US", "Model call")):
        stages = {s["name"]: s["label"] for s in build_topology(locale)["stages"]}
        assert stages["model"] == expected
        for name, label in stages.items():
            assert label != f"pipeline.stage.{name}", f"{name} 在 {locale} 缺少标签"


def test_correct_order_has_no_violations() -> None:
    assert violated_constraints(list(STAGE_ORDER)) == []


def test_swapping_two_constrained_stages_is_reported() -> None:
    order = list(STAGE_ORDER)
    i, j = order.index("sanitize"), order.index("injection_screen")
    order[i], order[j] = order[j], order[i]

    violations = violated_constraints(order)
    assert any(v["before"] == "sanitize" and v["after"] == "injection_screen" for v in violations)
    assert all(v["why"] for v in violations), "违规必须带具体理由，不能只说「不安全」"


def test_reordering_unconstrained_stages_is_safe() -> None:
    order = list(STAGE_ORDER)
    i, j = order.index("recall"), order.index("knowledge")
    order[i], order[j] = order[j], order[i]
    assert violated_constraints(order) == []


def test_missing_stages_are_skipped_not_crashed() -> None:
    """A partial order (the sandbox after a drag) must not raise."""
    assert violated_constraints(["dedup", "model"]) == []


# ------------------------------------------------------------------- endpoints


@pytest.fixture
def traced_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from soapbot.app import create_app
    from soapbot.config import settings

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "enable_runtime", False)

    store = TraceStore()
    _feed(store, _Ctx([("dedup", 0.4), ("model", 120.0)], trace_id="abc"))

    import soapbot.app as app_module

    class _Runtime:
        traces = store

    monkeypatch.setattr(app_module, "_RUNTIME", _Runtime())
    return TestClient(create_app())


def test_topology_endpoint(traced_client) -> None:
    body = traced_client.get("/api/pipeline/topology").json()
    assert len(body["stages"]) == len(STAGE_ORDER)
    assert body["reorderable"] is False


def test_traces_endpoint_returns_recent(traced_client) -> None:
    body = traced_client.get("/api/pipeline/traces?limit=10").json()
    assert body["traces"][0]["trace_id"] == "abc"
    assert body["traces"][0]["slowest"]["name"] == "model"
    assert body["summary"]["historical"] is False


def test_trace_detail_404_for_evicted(traced_client) -> None:
    response = traced_client.get("/api/pipeline/traces/does-not-exist")
    assert response.status_code == 404
    assert "缓冲区" in response.json()["detail"]


def test_metrics_endpoint(traced_client) -> None:
    body = traced_client.get("/api/pipeline/metrics").json()
    assert body["samples"]
    assert body["interval_seconds"] == 5


def test_reorder_check_names_the_broken_invariant(traced_client) -> None:
    order = list(STAGE_ORDER)
    i, j = order.index("guard"), order.index("whitelist")
    order[i], order[j] = order[j], order[i]

    body = traced_client.post("/api/pipeline/reorder-check", json={"order": order}).json()
    assert body["safe"] is False
    assert body["applies_to_runtime"] is False
    assert any(v["before"] == "guard" for v in body["violations"])


def test_reorder_check_rejects_unknown_stage(traced_client) -> None:
    response = traced_client.post(
        "/api/pipeline/reorder-check", json={"order": ["dedup", "not_a_stage"]}
    )
    assert response.status_code == 422


def test_trace_endpoints_503_without_collector(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import soapbot.app as app_module
    from soapbot.app import create_app
    from soapbot.config import settings

    config_dir = tmp_path / "cfg2"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "enable_runtime", False)

    class _Runtime:
        traces = None

    monkeypatch.setattr(app_module, "_RUNTIME", _Runtime())
    client = TestClient(create_app())

    assert client.get("/api/pipeline/traces").status_code == 503
    assert client.get("/api/pipeline/topology").status_code == 200
