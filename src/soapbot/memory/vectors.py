"""Batched cosine ranking over the float32 BLOBs stored in SQLite.

Why this module
---------------
Both recall channels (long-term memory and the RAG knowledge base) used to load
*every* row as a full ORM object, then call ``np.frombuffer``, ``np.linalg.norm``
and ``np.dot`` once per row in a Python loop. At a few thousand rows that is a
few thousand Python-to-C round trips plus thousands of ORM objects holding text
nobody was going to read — on every recalled turn.

``memory/db.py`` deliberately keeps brute-force cosine instead of a vector
database ("thousands of rows, not millions"). This module honours that decision:
same full scan, same cosine, same ranking. What changes is one matrix multiply
instead of N dot products, and letting callers fetch only ``(id, blob, dim)``
before they know which rows they actually need.

Keeping the NaN handling here rather than at each call site is the point. A
single NaN makes every comparison false, so ``cosine <= 0`` never fires and the
ranking becomes arbitrary instead of empty — the knowledge-base path had no
guard at all. One function means one place to get it right.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

#: A stored vector is ``float32``; :func:`soapbot.memory.db.vector_to_blob` writes it.
#: ``struct.calcsize`` rather than ``np.dtype(...).itemsize`` on purpose: this module
#: is imported by ``memory.store``, which hundreds of short-lived CLI/gate subprocesses
#: import. A *module-level* numpy import there makes every one of them pay numpy's
#: startup cost even when no vector is ever scored. numpy is loaded inside
#: :func:`rank_by_cosine`, exactly as ``memory.db.vector_to_blob`` already does.
_ITEMSIZE = struct.calcsize("f")


class VectorCandidate(NamedTuple):
    """The only three columns a scan needs before top-N is known."""

    id: int
    blob: bytes | None
    dim: int


@dataclass(frozen=True, slots=True)
class CosineRanking:
    """``hits`` is ordered best-first and already truncated to ``limit``.

    ``query_usable`` is separate from an empty result: a broken *query* is a
    provider problem worth a warning, while a healthy query over no usable rows
    is an ordinary keyword-only recall. ``dropped`` counts rows that could not
    be scored, so a corrupt corpus is visible in the logs instead of looking
    like "memory does not work".
    """

    hits: list[tuple[float, int]]
    dropped: int
    query_usable: bool
    #: Valid vectors whose cosine was <= 0. These are ordinary "not relevant"
    #: rows, not corruption: roughly half of a random corpus, on every query.
    #: Kept separate so the warning about unusable embeddings means something.
    non_positive: int = 0


def rank_by_cosine(
    candidates: Iterable[VectorCandidate], query: list[float], *, limit: int
) -> CosineRanking:
    """Score every candidate against ``query`` and return the top ``limit`` ids.

    Rows are rejected (and counted) when the dim does not match the query, the
    blob length does not match the declared dim, or the vector/norm/cosine is
    not finite and positive. Ties keep scan order, matching the old stable
    ``list.sort(reverse=True)`` so RRF ranks do not shift on equal scores.
    """
    import numpy as np

    q = np.asarray(query, dtype=np.float32)
    if q.ndim != 1 or q.size == 0 or not np.all(np.isfinite(q)):
        return CosineRanking([], 0, False)
    qn = float(np.linalg.norm(q))
    if qn == 0 or not np.isfinite(qn):
        return CosineRanking([], 0, False)

    ids: list[int] = []
    blobs: list[bytes] = []
    dropped = 0
    for candidate in candidates:
        if (
            not candidate.blob
            or candidate.dim != q.size
            or len(candidate.blob) != candidate.dim * _ITEMSIZE
        ):
            dropped += 1
            continue
        ids.append(candidate.id)
        blobs.append(candidate.blob)
    if not ids:
        return CosineRanking([], dropped, True)

    # One concatenation and one reshape, rather than N frombuffer calls. Every
    # blob was checked for the exact byte length above, so the shape is safe.
    matrix = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(ids), q.size)
    finite = np.isfinite(matrix).all(axis=1)
    # Zero out non-finite rows *before* the norm and dot product: NaN/inf would
    # otherwise spread through the whole reduction and poison unrelated rows.
    clean = np.where(finite[:, None], matrix, np.float32(0.0))
    norms = np.linalg.norm(clean, axis=1)
    dots = clean @ q
    with np.errstate(divide="ignore", invalid="ignore"):
        cosines = dots / (qn * norms)
    usable = finite & (norms > 0) & np.isfinite(norms) & np.isfinite(cosines)
    non_positive = int((usable & (cosines <= 0)).sum())
    dropped += int((~usable).sum())
    good = usable & (cosines > 0)

    cosines = np.where(good, cosines, -np.inf)
    order = np.argsort(-cosines, kind="stable")
    hits = [
        (float(cosines[index]), ids[index])
        for index in order[: min(max(0, limit), int(good.sum()))]
    ]
    return CosineRanking(hits, dropped, True, non_positive)


__all__ = ["CosineRanking", "VectorCandidate", "rank_by_cosine"]
