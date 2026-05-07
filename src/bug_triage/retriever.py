"""Retrieve similar past resolutions via cosine similarity.

In-Postgres retrieval uses pgvector's ``<=>`` cosine-distance operator. There
is also a pure-Python fallback that lets unit tests assert the cosine math
without spinning up a database.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bug_triage.embedder import Embedder
from bug_triage.models import Resolution


@dataclass(frozen=True)
class ResolutionMatch:
    resolution_id: str
    similarity: float
    severity: str
    component: str
    bug_report: str
    root_cause: str
    fix_diff: str
    files_changed: list[str]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, robust to zero vectors."""
    if len(a) != len(b):
        raise ValueError(f"vector dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def retrieve(
    session: Session,
    embedder: Embedder,
    bug_report: str,
    *,
    k: int = 3,
) -> list[ResolutionMatch]:
    """Embed ``bug_report`` and return the top-k similar resolutions."""

    query_vec = embedder.embed(bug_report)
    stmt = (
        select(Resolution, Resolution.embedding.cosine_distance(query_vec).label("distance"))
        .where(Resolution.embedding.is_not(None))
        .order_by("distance")
        .limit(k)
    )
    rows = session.execute(stmt).all()
    return [
        ResolutionMatch(
            resolution_id=row.Resolution.id,
            similarity=1.0 - float(row.distance),
            severity=row.Resolution.severity,
            component=row.Resolution.component,
            bug_report=row.Resolution.bug_report,
            root_cause=row.Resolution.root_cause,
            fix_diff=row.Resolution.fix_diff,
            files_changed=list(row.Resolution.files_changed),
        )
        for row in rows
    ]


def retrieve_in_memory(
    resolutions: list[Resolution],
    embedder: Embedder,
    bug_report: str,
    *,
    k: int = 3,
) -> list[ResolutionMatch]:
    """Same retrieval semantics, no database. Used by eval-smoke and tests."""

    query_vec = embedder.embed(bug_report)
    scored: list[tuple[float, Resolution]] = []
    for r in resolutions:
        if r.embedding is None:
            continue
        sim = cosine_similarity(query_vec, list(r.embedding))
        scored.append((sim, r))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        ResolutionMatch(
            resolution_id=r.id,
            similarity=float(sim),
            severity=r.severity,
            component=r.component,
            bug_report=r.bug_report,
            root_cause=r.root_cause,
            fix_diff=r.fix_diff,
            files_changed=list(r.files_changed),
        )
        for sim, r in scored[:k]
    ]
