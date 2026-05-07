"""Eval smoke test gated on RUN_EVAL_SMOKE=1.

Runs the 20-case ``triage_v1`` suite end-to-end via FakeProvider and
HashEmbedder. Asserts the pipeline doesn't crash and that retrieval quality
clears the documented thresholds.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import HashEmbedder
from bug_triage.eval_harness import run_eval
from bug_triage.providers.fake import FakeProvider

REPO_ROOT = Path(__file__).resolve().parents[2]


def _enabled() -> bool:
    return os.environ.get("RUN_EVAL_SMOKE") == "1"


@pytest.mark.eval_smoke
@pytest.mark.skipif(not _enabled(), reason="set RUN_EVAL_SMOKE=1 to run")
def test_eval_smoke_meets_thresholds() -> None:
    embedder = HashEmbedder()
    rows = load_resolutions(REPO_ROOT / "corpus" / "resolutions")
    embed_resolutions(rows, embedder)
    report = run_eval(
        suite_path=REPO_ROOT / "eval" / "suites" / "triage_v1.yaml",
        provider=FakeProvider(),
        embedder=embedder,
        resolutions=rows,
        repo_root=REPO_ROOT,
    )
    assert report.n == 20
    assert report.top3_retrieval_match >= 0.6
    assert report.suggested_diff_parses >= 0.9
