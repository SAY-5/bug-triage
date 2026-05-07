"""Load resolution exemplars from disk into ``Resolution`` rows."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bug_triage.embedder import Embedder
from bug_triage.models import Resolution


def iter_resolution_files(root: Path) -> list[Path]:
    return sorted(root.glob("R*.json"))


def load_resolutions(root: Path) -> list[Resolution]:
    """Load resolution JSON files, without running an embedder."""

    rows: list[Resolution] = []
    for path in iter_resolution_files(root):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            Resolution(
                id=str(data["id"]),
                bug_report=str(data["bug_report"]),
                root_cause=str(data["root_cause"]),
                fix_diff=str(data["fix_diff"]),
                files_changed=list(data["files_changed"]),
                severity=str(data["severity"]),
                component=str(data["component"]),
                resolved_at=datetime.fromisoformat(str(data["resolved_at"])),
            )
        )
    return rows


def embed_resolutions(rows: list[Resolution], embedder: Embedder) -> None:
    """Populate the ``embedding`` column in place."""

    for r in rows:
        text = f"{r.bug_report}\n\n{r.root_cause}"
        r.embedding = embedder.embed(text)
