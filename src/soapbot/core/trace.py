"""Recent pipeline traces and a rolling metric series.

The gap this fills
------------------
``PipelineContext.timings`` is populated on every message — one entry per stage, in
milliseconds — and then thrown away when the request ends. The dashboard could
therefore show *cumulative counters* (inbound / handled / halted) but not a single
question an operator actually asks during an incident:

    "the reply took 9 seconds, which stage was it"

Answering that from counters is impossible; the information existed and was
discarded. This module keeps the last N traces so the answer is available for the
window that matters.

Why an in-memory ring and not the database
------------------------------------------
* **Bounded by construction.** ``deque(maxlen=N)`` cannot grow, so there is no cleanup
  job, no retention policy, and no way for a busy group to fill the disk.
* **Lost on restart, which is correct here.** Traces answer "what just happened". The
  durable record of *decisions* is the audit log, which already exists and is written
  for a different purpose. Duplicating traces into SQLite would add a write per
  message on the hot path to serve a query nobody runs after a restart.
* **No sampling.** The usual argument for sampling is volume, but the ring is already
  capped at 500 messages — roughly the last few minutes of a busy group. Sampling
  would drop precisely the slow request someone is looking for, and a trace you cannot
  find is worse than one you never stored, because you will keep looking.

Per-stage timing is recorded by the pipeline's existing observer hook, and the whole
trace is assembled when ``message.processed`` fires. Nothing in ``Pipeline`` is
modified: it already publishes everything needed.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from soapbot.i18n import t

logger = logging.getLogger(__name__)

#: How many traces to keep. 500 covers several minutes in a busy group and costs
#: roughly 300 KB at the sizes seen in practice.
DEFAULT_TRACE_CAPACITY = 500

#: Metric samples. One per ``METRIC_INTERVAL`` seconds, keeping a rolling hour.
DEFAULT_METRIC_POINTS = 720
METRIC_INTERVAL = 5.0

#: Stage names in the order ``build_pipeline`` assembles them.
#:
#: Duplicated from ``builder.py`` on purpose, and pinned by a test that compares the
#: two. Importing it would create a cycle (builder imports the runtime, which imports
#: this), and generating it would make the graph silently follow any reordering —
#: including an accidental one. A test that fails when they drift is the only version
#: of this list that stays true.
STAGE_ORDER: tuple[str, ...] = (
    "dedup",
    "guard",
    "whitelist",
    "wake",
    "strip_wake",
    "sanitize",
    "injection_screen",
    "authorization",
    "command",
    "plugin_command",
    "plugin_message_hooks",
    "persist",
    "persona",
    "recall",
    "knowledge",
    "model",
    "safety",
    "reply",
    "persist_reply",
    "memory_write",
)

#: Why each ordering constraint exists, keyed by the pair it constrains.
#:
#: Taken from ``docs/architecture.md``. Kept as data rather than prose so the sandbox
#: reorder view can point at the specific rule a hypothetical order would break —
#: "this is unsafe" without saying which invariant is just a warning label.
ORDER_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("guard", "whitelist"),
    ("wake", "strip_wake"),
    ("strip_wake", "sanitize"),
    ("sanitize", "injection_screen"),
    ("injection_screen", "command"),
    ("authorization", "command"),
    ("command", "persist"),
    ("persist", "model"),
    ("safety", "reply"),
)


def stage_label(name: str, locale: str | None = None) -> str:
    """Human name for a stage, translated on the way out.

    The labels and the reasons below used to be Chinese constants in this module. They
    are now catalogue entries because they are read by an operator in the panel, which
    is a translated surface — leaving them here meant the English panel showed a graph
    whose reasons were in Chinese, which is the half-translated state this page spent
    effort escaping.
    """
    return t(f"pipeline.stage.{name}", locale)


def constraint_reason(before: str, after: str, locale: str | None = None) -> str:
    return t(f"pipeline.constraint.{before}.{after}", locale)


@dataclass(slots=True)
class StageTrace:
    """One stage's contribution to one message."""

    name: str
    elapsed_ms: float
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "elapsed_ms": round(self.elapsed_ms, 3), "order": self.order}


@dataclass(slots=True)
class MessageTrace:
    """Everything the panel shows about a single processed message."""

    trace_id: str
    ts: float
    session_key: str
    total_ms: float
    halted: bool
    halt_reason: str
    stages: list[StageTrace] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    chunks: list[str] = field(default_factory=list)
    """Sentences actually delivered, in order.

    Empty when the reply went out as a single message. Kept as its own field rather
    than inside ``extras`` because ``extras`` is filtered to scalars (it is copied to
    bound memory for every trace) and a list would silently disappear from it.
    """

    stream: dict[str, Any] = field(default_factory=dict)
    """Progressive-delivery timings: first token, first send, interruption."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "ts": self.ts,
            "session_key": self.session_key,
            "total_ms": round(self.total_ms, 3),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "stages": [s.to_dict() for s in self.stages],
            "slowest": self.slowest(),
            "chunks": list(self.chunks),
            "stream": dict(self.stream),
        }

    def slowest(self) -> dict[str, Any] | None:
        if not self.stages:
            return None
        stage = max(self.stages, key=lambda s: s.elapsed_ms)
        return {"name": stage.name, "elapsed_ms": round(stage.elapsed_ms, 3)}


@dataclass(slots=True)
class MetricSample:
    ts: float
    handled: int
    halted: int
    failed: int
    p50_ms: float
    p95_ms: float
    max_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": round(self.ts, 3),
            "handled": self.handled,
            "halted": self.halted,
            "failed": self.failed,
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


def _percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile.

    Not interpolation: with 20–500 samples the interpolated value describes a point
    between two observations, and an operator reading "p95 = 812.4ms" reasonably
    assumes some request took 812.4ms. Nearest-rank returns an observed value.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


class TraceStore:
    """Ring of recent traces plus a rolling metric series.

    Fed by two things the runtime already emits:

    * ``pipeline.observe`` gives per-stage timings as they happen;
    * ``bus`` publishes ``message.processed`` with the finished context.

    The store keeps its own per-trace scratch so it does not have to be re-entrant
    with the pipeline: ``observe`` appends to ``_pending``, and ``message.processed``
    promotes it into a :class:`MessageTrace`.
    """

    def __init__(
        self,
        capacity: int = DEFAULT_TRACE_CAPACITY,
        metric_points: int = DEFAULT_METRIC_POINTS,
    ) -> None:
        self._traces: deque[MessageTrace] = deque(maxlen=capacity)
        self._metrics: deque[MetricSample] = deque(maxlen=metric_points)
        self._pending: dict[str, MessageTrace] = {}
        self._durations: deque[float] = deque(maxlen=capacity)
        self._last_sample = 0.0
        self.counters = {"handled": 0, "halted": 0, "failed": 0}

    # ------------------------------------------------------------- ingestion

    def observe_stage(self, ctx: Any, stage: Any, elapsed_ms: float) -> None:
        """Record one stage. Matches ``Pipeline.observe``'s callback signature.

        Never raises: it runs inside the pipeline's ``finally`` block, and a
        diagnostics collector that breaks message delivery is worse than no collector.
        ``Pipeline.observe`` already swallows exceptions, but being explicit here keeps
        the contract visible at the call site that would violate it.
        """
        try:
            trace_id = str(getattr(getattr(ctx, "event", None), "trace_id", "") or "")
            if not trace_id:
                return
            trace = self._pending.get(trace_id)
            if trace is None:
                trace = MessageTrace(
                    trace_id=trace_id,
                    ts=time.time(),
                    session_key=str(getattr(getattr(ctx, "event", None), "session_key", "")),
                    total_ms=0.0,
                    halted=False,
                    halt_reason="",
                )
                self._pending[trace_id] = trace
            name = str(getattr(stage, "name", stage))
            trace.stages.append(
                StageTrace(name=name, elapsed_ms=float(elapsed_ms), order=_stage_order(name))
            )
        except Exception:  # pragma: no cover - defensive
            logger.debug("trace observe failed", exc_info=True)

    def on_processed(self, ctx: Any) -> None:
        """Promote a finished context into a stored trace and refresh metrics."""
        trace_id = str(getattr(getattr(ctx, "event", None), "trace_id", "") or "")
        trace = self._pending.pop(trace_id, None)
        if trace is None:
            # No stage was observed (a context that never entered the pipeline, or a
            # halt before the first stage). Still worth keeping: it is the case where
            # the operator most wants to know that nothing ran.
            trace = MessageTrace(
                trace_id=trace_id,
                ts=getattr(ctx, "started_at", time.time()),
                session_key=str(getattr(getattr(ctx, "event", None), "session_key", "")),
                total_ms=0.0,
                halted=bool(getattr(ctx, "halted", False)),
                halt_reason=str(getattr(ctx, "halt_reason", "")),
            )

        trace.halted = bool(getattr(ctx, "halted", False))
        trace.halt_reason = str(getattr(ctx, "halt_reason", ""))
        timings = getattr(ctx, "timings", {}) or {}
        if timings:
            trace.total_ms = float(sum(timings.values()))
        else:
            trace.total_ms = float(sum(s.elapsed_ms for s in trace.stages))
        trace.stages.sort(key=lambda s: s.order)

        if trace.halted:
            self.counters["halted"] += 1
        else:
            self.counters["handled"] += 1
        self._durations.append(trace.total_ms)

        # Contexts carry a bounded, redacted `extras` mapping; copying only scalars
        # keeps a large payload from pinning memory for the life of the ring.
        extras = getattr(ctx, "extras", {}) or {}
        trace.extras = {
            k: v for k, v in extras.items() if isinstance(v, str | int | float | bool)
        }
        trace.chunks = [str(c) for c in (extras.get("reply_chunks") or [])]
        stream = extras.get("stream")
        if isinstance(stream, dict):
            # Whitelisted, not copied: this dict comes from model output and would be
            # stored verbatim for the life of the ring buffer otherwise.
            trace.stream = {
                key: stream.get(key)
                for key in (
                    "count",
                    "chars",
                    "first_token_ms",
                    "first_send_ms",
                    "total_ms",
                    "interrupted",
                    "truncated",
                )
            }
        self._traces.append(trace)
        self._maybe_sample()

    def note_failure(self, ctx: Any = None) -> None:
        """Record a message that crashed the pipeline.

        Kept as a trace rather than a bare counter: "3 failures" tells an operator
        nothing, while the stage list up to the crash tells them where to look. The
        trace is marked ``halted`` with a ``pipeline_error`` reason so the panel does
        not render it as a clean stop.
        """
        self.counters["failed"] += 1
        if ctx is None:
            return
        trace_id = str(getattr(getattr(ctx, "event", None), "trace_id", "") or "")
        trace = self._pending.pop(trace_id, None)
        if trace is None:
            trace = MessageTrace(
                trace_id=trace_id,
                ts=getattr(ctx, "started_at", time.time()),
                session_key=str(getattr(getattr(ctx, "event", None), "session_key", "")),
                total_ms=0.0,
                halted=True,
                halt_reason="pipeline_error",
            )
        trace.halted = True
        trace.halt_reason = trace.halt_reason or "pipeline_error"
        trace.total_ms = float(sum(s.elapsed_ms for s in trace.stages))
        trace.stages.sort(key=lambda s: s.order)
        trace.extras = {"error": True}
        self._traces.append(trace)

    def _maybe_sample(self) -> None:
        now = time.time()
        if now - self._last_sample < METRIC_INTERVAL and self._metrics:
            return
        self._last_sample = now
        durations = list(self._durations)
        self._metrics.append(
            MetricSample(
                ts=now,
                handled=self.counters["handled"],
                halted=self.counters["halted"],
                failed=self.counters["failed"],
                p50_ms=_percentile(durations, 0.50),
                p95_ms=_percentile(durations, 0.95),
                max_ms=max(durations) if durations else 0.0,
            )
        )

    # ---------------------------------------------------------------- reading

    def recent(self, limit: int = 50) -> list[MessageTrace]:
        """Newest first. A reversed ring copy, not a slice of a sorted list."""
        items = list(self._traces)[-limit:]
        items.reverse()
        return items

    def by_trace(self, trace_id: str) -> MessageTrace | None:
        for trace in reversed(self._traces):
            if trace.trace_id == trace_id:
                return trace
        return None

    def metrics(self, limit: int = DEFAULT_METRIC_POINTS) -> list[MetricSample]:
        return list(self._metrics)[-limit:]

    def summary(self) -> dict[str, Any]:
        durations = list(self._durations)
        return {
            "traces_kept": len(self._traces),
            "counters": dict(self.counters),
            "p50_ms": round(_percentile(durations, 0.50), 2),
            "p95_ms": round(_percentile(durations, 0.95), 2),
            "max_ms": round(max(durations), 2) if durations else 0.0,
            # Stated in the payload rather than only in the docs: a consumer that
            # renders "0 ms" without this would report a missing feature as a fast one.
            "historical": False,
            "note": "仅保留最近若干条，重启即清空；历史查询请用审计日志",
        }

    def clear(self) -> None:
        self._traces.clear()
        self._metrics.clear()
        self._pending.clear()
        self._durations.clear()
        self.counters = {"handled": 0, "halted": 0, "failed": 0}
        self._last_sample = 0.0


def _stage_order(name: str) -> int:
    try:
        return STAGE_ORDER.index(name)
    except ValueError:
        # A stage not in the known list still gets a stable position at the end
        # instead of raising; the wiring test is what reports the drift.
        return len(STAGE_ORDER)


def build_topology(locale: str | None = None) -> dict[str, Any]:
    """The graph the panel draws: stages in order, plus the constraints between them.

    ``locale`` is passed rather than read from a global: one process serves several
    panels, and a module-level "current language" would make the answer depend on which
    request arrived last.
    """
    return {
        "stages": [
            {"name": name, "label": stage_label(name, locale), "order": index}
            for index, name in enumerate(STAGE_ORDER)
        ],
        "constraints": [
            {"before": before, "after": after, "why": constraint_reason(before, after, locale)}
            for before, after in ORDER_CONSTRAINTS
        ],
        "reorderable": False,
        "note": t("pipeline.note", locale),
    }


def violated_constraints(order: list[str], locale: str | None = None) -> list[dict[str, str]]:
    """Which documented constraints a hypothetical order breaks.

    Powers the sandbox view: an operator can drag stages around and see the specific
    invariant that would break, instead of a generic "unsafe" label. The result is
    never written back — ``build_pipeline`` is the only place that decides order.
    """
    position = {name: index for index, name in enumerate(order)}
    broken: list[dict[str, str]] = []
    for before, after in ORDER_CONSTRAINTS:
        if before not in position or after not in position:
            continue
        if position[before] > position[after]:
            broken.append(
                {
                    "before": before,
                    "after": after,
                    "why": constraint_reason(before, after, locale),
                }
            )
    return broken
