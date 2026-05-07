"""Load resolutions into Postgres + pgvector. Idempotent."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import build_embedder
from bug_triage.models import Resolution
from bug_triage.settings import get_settings


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    embedder = build_embedder(prefer_hash=settings.hash_embedder)
    rows = load_resolutions(settings.corpus_root / "resolutions")
    embed_resolutions(rows, embedder)
    with Session(engine) as session:
        for r in rows:
            existing = session.get(Resolution, r.id)
            if existing is None:
                session.add(r)
            else:
                existing.bug_report = r.bug_report
                existing.root_cause = r.root_cause
                existing.fix_diff = r.fix_diff
                existing.files_changed = r.files_changed
                existing.severity = r.severity
                existing.component = r.component
                existing.resolved_at = r.resolved_at
                existing.embedding = r.embedding
        session.commit()
    print(f"seeded {len(rows)} resolutions into {settings.database_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
