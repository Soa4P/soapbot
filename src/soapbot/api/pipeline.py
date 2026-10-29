"""Read-only views of the pipeline: topology, recent traces, metric series.

All three are GETs. Reordering the pipeline is not exposed, and that is a decision
rather than an omission: the stage order *is* the security model — ``guard`` before
``whitelist``, ``sanitize`` before ``injection_screen``, ``safety`` before ``reply``.
A drag-and-drop editor for it would look like a workflow tool and would let one
accidental save remove the injection screen from the live path.

What the panel does instead is a **sandbox**: ``POST /api/pipeline/reorder-check``
takes a proposed order and reports which documented constraints it would break. It
writes nothing, touches no runtime object, and its answer names the specific invariant
rather than saying "unsafe" — because a warning that cannot be explained gets clicked
through.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from soapbot.api.auth import require_api_auth
from soapbot.api.locale import request_locale
from soapbot.core.trace import build_topology, violated_constraints
from soapbot.i18n import t

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _runtime():
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime


def _traces():
    runtime = _runtime()
    store = getattr(runtime, "traces", None)
    if store is None:
        # Distinct from "no traces yet": a missing collector means the runtime was
        # assembled without one, so an empty list would be a lie about a working
        # feature rather than an accurate "nothing processed".
        raise HTTPException(status_code=503, detail="trace collector is not attached")
    return store


@router.get("/topology")
async def topology(_: dict[str, Any] = Depends(require_api_auth)) -> dict[str, Any]:
    """Stages in assembly order, plus the constraints between them.

    The order comes from ``core/trace.py::STAGE_ORDER``, which a test pins against
    ``build_pipeline``. Serving it from the runtime object instead would describe one
    instance; serving it from the builder would require importing the builder here and
    risk a cycle.
    """
    return build_topology()


class ReorderCheckRequest(BaseModel):
    order: list[str] = Field(..., min_length=1, max_length=64)


@router.post("/reorder-check")
async def reorder_check(
    payload: ReorderCheckRequest,
    _: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Report which invariants a hypothetical stage order would violate.

    Stateless and write-free. This is the only "reordering" the panel offers, and it
    answers a question ("why can't I move this?") that a disabled drag handle cannot.
    """
    unknown = [name for name in payload.order if name not in build_topology_names()]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"未知的 Stage 名称：{', '.join(sorted(unknown))}",
        )
    broken = violated_constraints(payload.order)
    return {
        "order": payload.order,
        "violations": broken,
        "safe": not broken,
        # Stated in every response so a client cannot render the sandbox as a real
        # editor: the sandbox result is a teaching aid, not a pending change.
        "applies_to_runtime": False,
    }


def build_topology_names() -> set[str]:
    from soapbot.core.trace import STAGE_ORDER

    return set(STAGE_ORDER)


@router.get("/traces")
async def traces(
    limit: int = Query(50, ge=1, le=200),
    _: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Recent traces, newest first, with a per-stage breakdown."""
    store = _traces()
    return {
        "traces": [t.to_dict() for t in store.recent(limit)],
        "summary": store.summary(),
    }


@router.get("/traces/{trace_id}")
async def trace_detail(
    trace_id: str,
    request: Request,
    _: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    if len(trace_id) > 128:
        raise HTTPException(status_code=422, detail=t("api.trace_too_long", request_locale(request)))
    store = _traces()
    trace = store.by_trace(trace_id)
    if trace is None:
        # 404 rather than an empty object: a trace that has aged out of the ring is
        # genuinely gone, and the panel should say "已滚出缓冲区" instead of drawing
        # an empty stage list that looks like a message that did nothing.
        raise HTTPException(
            status_code=404, detail=t("api.trace_not_found", request_locale(request))
        )
    return trace.to_dict()


@router.get("/metrics")
async def metrics(
    limit: int = Query(720, ge=1, le=720),
    _: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    store = _traces()
    return {
        "samples": [s.to_dict() for s in store.metrics(limit)],
        "summary": store.summary(),
        "interval_seconds": 5,
    }
