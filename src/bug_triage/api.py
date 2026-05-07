"""FastAPI surface for triage."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from bug_triage.classifier import ClassifierResult
from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import Embedder, build_embedder
from bug_triage.models import Resolution, TriageResult
from bug_triage.pipeline import run_triage
from bug_triage.providers import build_provider
from bug_triage.providers.base import ChatProvider
from bug_triage.retriever import ResolutionMatch
from bug_triage.settings import Settings, get_settings
from bug_triage.suggester import SuggestionResult

log = logging.getLogger("bug_triage.api")


class _AppState:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    provider: ChatProvider
    embedder: Embedder
    resolutions: list[Resolution]


state = _AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state.settings = settings
    state.engine = create_engine(settings.database_url, future=True)
    state.session_factory = sessionmaker(state.engine, expire_on_commit=False)
    state.provider = build_provider(settings.provider)
    state.embedder = build_embedder(prefer_hash=settings.hash_embedder)
    rows = load_resolutions(settings.corpus_root / "resolutions")
    embed_resolutions(rows, state.embedder)
    state.resolutions = rows
    log.info("loaded %d resolutions; provider=%s", len(rows), state.provider.name)
    yield


app = FastAPI(title="bug-triage", version="0.1.0", lifespan=lifespan)


class TriageRequest(BaseModel):
    bug_report: str = Field(min_length=1, max_length=10_000)


class TriageResponse(BaseModel):
    triage_id: int | None
    classification: dict[str, object]
    retrieved: list[dict[str, object]]
    suggestion: dict[str, object]
    latency_ms: int


class ResolutionView(BaseModel):
    id: str
    severity: str
    component: str
    bug_report: str
    files_changed: list[str]


class ResolutionsPage(BaseModel):
    items: list[ResolutionView]
    next_cursor: str | None


def _session() -> Session:
    return state.session_factory()


def _provider() -> ChatProvider:
    return state.provider


def _embedder() -> Embedder:
    return state.embedder


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/triage", response_model=TriageResponse)
def triage(
    body: TriageRequest,
    provider: Annotated[ChatProvider, Depends(_provider)],
    embedder: Annotated[Embedder, Depends(_embedder)],
) -> TriageResponse:
    outcome = run_triage(
        provider=provider,
        embedder=embedder,
        resolutions=state.resolutions,
        bug_report=body.bug_report,
        repo_root=state.settings.repo_root,
    )
    triage_id = _persist(
        outcome.bug_report,
        outcome.classification,
        outcome.retrieved,
        outcome.suggestion,
        outcome.latency_ms,
    )
    return TriageResponse(
        triage_id=triage_id,
        classification=outcome.classification.output.model_dump(),
        retrieved=[_match_view(m) for m in outcome.retrieved],
        suggestion=outcome.suggestion.output.model_dump(),
        latency_ms=outcome.latency_ms,
    )


def _match_view(m: ResolutionMatch) -> dict[str, object]:
    return {
        "resolution_id": m.resolution_id,
        "similarity": round(m.similarity, 4),
        "severity": m.severity,
        "component": m.component,
        "bug_report": m.bug_report,
        "files_changed": m.files_changed,
    }


def _persist(
    bug_report: str,
    classification: ClassifierResult,
    retrieved: list[ResolutionMatch],
    suggestion: SuggestionResult,
    latency_ms: int,
) -> int | None:
    try:
        with _session() as session:
            row = TriageResult(
                incoming_bug=bug_report,
                classification=classification.output.model_dump(),
                retrieved_ids=[m.resolution_id for m in retrieved],
                suggestion=suggestion.output.model_dump(),
                model_version=classification.model_version,
                total_cost_usd=0.0,
                total_latency_ms=latency_ms,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        log.warning("failed to persist triage result: %s", exc)
        return None


@app.get("/v1/triage/{triage_id}", response_model=TriageResponse)
def get_triage(triage_id: int) -> TriageResponse:
    try:
        with _session() as session:
            row = session.get(TriageResult, triage_id)
            if row is None:
                raise HTTPException(status_code=404, detail="triage_id not found")
            return TriageResponse(
                triage_id=int(row.id),
                classification=row.classification,
                retrieved=[{"resolution_id": rid} for rid in row.retrieved_ids],
                suggestion=row.suggestion,
                latency_ms=row.total_latency_ms,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as 503 rather than 500
        log.warning("get_triage failed: %s", exc)
        raise HTTPException(status_code=503, detail="persistence unavailable") from exc


@app.get("/v1/resolutions", response_model=ResolutionsPage)
def list_resolutions(
    cursor: str | None = Query(default=None),
    component: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> ResolutionsPage:
    try:
        with _session() as session:
            stmt = select(Resolution).order_by(Resolution.id)
            if cursor is not None:
                stmt = stmt.where(Resolution.id > cursor)
            if component is not None:
                stmt = stmt.where(Resolution.component == component)
            if severity is not None:
                stmt = stmt.where(Resolution.severity == severity)
            stmt = stmt.limit(limit + 1)
            rows = session.execute(stmt).scalars().all()
            has_more = len(rows) > limit
            items = rows[:limit]
            return ResolutionsPage(
                items=[
                    ResolutionView(
                        id=r.id,
                        severity=r.severity,
                        component=r.component,
                        bug_report=r.bug_report,
                        files_changed=list(r.files_changed),
                    )
                    for r in items
                ],
                next_cursor=items[-1].id if has_more and items else None,
            )
    except Exception as exc:  # noqa: BLE001 - surface as 503 rather than 500
        log.warning("list_resolutions failed: %s", exc)
        raise HTTPException(status_code=503, detail="persistence unavailable") from exc
