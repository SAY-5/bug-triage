"""End-to-end pipeline against FakeProvider + HashEmbedder."""

from __future__ import annotations

from pathlib import Path

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import HashEmbedder
from bug_triage.pipeline import run_triage
from bug_triage.providers.fake import FakeProvider

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pipeline_returns_classification_retrieved_and_diff() -> None:
    embedder = HashEmbedder()
    rows = load_resolutions(REPO_ROOT / "corpus" / "resolutions")
    embed_resolutions(rows, embedder)
    outcome = run_triage(
        provider=FakeProvider(),
        embedder=embedder,
        resolutions=rows,
        bug_report="Calculator.div returns Infinity instead of throwing on zero divisor at /div",
        repo_root=REPO_ROOT,
    )
    assert outcome.classification.output.severity in {"critical", "high", "medium", "low"}
    assert len(outcome.retrieved) == 3
    assert outcome.retrieved[0].resolution_id == "R001"
    assert outcome.suggestion.diff_parses is True
    assert outcome.latency_ms >= 0
