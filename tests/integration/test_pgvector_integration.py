"""pgvector integration test gated on RUN_INTEGRATION=1."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import HashEmbedder
from bug_triage.models import Base
from bug_triage.retriever import retrieve

REPO_ROOT = Path(__file__).resolve().parents[2]


def _enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _db_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://bug_triage:bug_triage@localhost:5432/bug_triage",
    )


@pytest.mark.integration
@pytest.mark.skipif(not _enabled(), reason="set RUN_INTEGRATION=1 to run")
def test_pgvector_round_trip_and_topk() -> None:
    engine = create_engine(_db_url(), future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    embedder = HashEmbedder()
    rows = load_resolutions(REPO_ROOT / "corpus" / "resolutions")
    embed_resolutions(rows, embedder)
    with Session(engine) as session:
        for r in rows[:5]:
            session.add(r)
        session.commit()
        matches = retrieve(
            session,
            embedder,
            "Calculator.div returns Infinity instead of throwing on zero divisor",
            k=3,
        )
        assert matches
        assert matches[0].resolution_id in {r.id for r in rows[:5]}
