"""Eval harness scoring + report rendering."""

from __future__ import annotations

import json
from pathlib import Path

from bug_triage.classifier import ClassifierOutput, ClassifierResult
from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import HashEmbedder
from bug_triage.eval_harness import (
    EvalCase,
    load_suite,
    report_to_dict,
    report_to_markdown,
    run_eval,
    score_case,
    write_report,
)
from bug_triage.pipeline import TriageOutcome
from bug_triage.providers.fake import FakeProvider
from bug_triage.retriever import ResolutionMatch
from bug_triage.suggester import SuggesterOutput, SuggestionResult

REPO_ROOT = Path(__file__).resolve().parents[2]


def _outcome() -> TriageOutcome:
    return TriageOutcome(
        bug_report="x",
        classification=ClassifierResult(
            output=ClassifierOutput(
                severity="high", component="core", confidence=0.8, reasoning="ok"
            ),
            raw_response="{}",
            model_version="fake-1",
            prompt_version="2026.05.01",
            low_confidence=False,
        ),
        retrieved=[
            ResolutionMatch(
                resolution_id="R001",
                similarity=0.9,
                severity="high",
                component="core",
                bug_report="x",
                root_cause="x",
                fix_diff="x",
                files_changed=["a"],
            ),
        ],
        suggestion=SuggestionResult(
            output=SuggesterOutput(
                suggested_diff="x",
                rationale="x",
                confidence=0.5,
                applies_to_files=["a", "b"],
                based_on_resolutions=["R001"],
            ),
            raw_response="{}",
            diff_parses=True,
            parse_error=None,
            model_version="fake-1",
            prompt_version="2026.05.01",
        ),
        latency_ms=1,
    )


def test_score_case_reports_each_metric() -> None:
    case = EvalCase(
        id="C01",
        bug_report="x",
        severity="high",
        component="core",
        expected_top1_resolution_id="R001",
        expected_files_changed=["a"],
    )
    score = score_case(case, _outcome())
    assert score.severity_match is True
    assert score.component_match is True
    assert score.top1_retrieval_match is True
    assert score.top3_retrieval_match is True
    assert score.suggested_diff_parses is True
    assert 0.0 < score.suggested_files_overlap <= 1.0


def test_run_eval_against_full_suite() -> None:
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
    assert report.top1_retrieval_match >= 0.6
    payload = report_to_dict(report)
    assert payload["metrics"]["top1_retrieval_match"] >= 0.6
    md = report_to_markdown(report)
    assert "top1_retrieval_match" in md


def test_load_suite_returns_twenty_cases() -> None:
    cases = load_suite(REPO_ROOT / "eval" / "suites" / "triage_v1.yaml")
    assert len(cases) == 20
    assert cases[0].id == "C01"


def test_write_report_round_trips(tmp_path: Path) -> None:
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
    out = tmp_path / "r.json"
    write_report(report, out)
    parsed = json.loads(out.read_text())
    assert parsed["n"] == 20
