"""Eval harness for the triage pipeline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from bug_triage.embedder import Embedder, build_embedder
from bug_triage.models import Resolution
from bug_triage.pipeline import TriageOutcome, run_triage
from bug_triage.providers import build_provider
from bug_triage.providers.base import ChatProvider


@dataclass(frozen=True)
class EvalCase:
    id: str
    bug_report: str
    severity: str
    component: str
    expected_top1_resolution_id: str
    expected_files_changed: list[str]


@dataclass
class CaseScore:
    case_id: str
    severity_match: bool
    component_match: bool
    top1_retrieval_match: bool
    top3_retrieval_match: bool
    suggested_diff_parses: bool
    suggested_files_overlap: float
    retrieved_ids: list[str]
    classification: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    suite: str
    provider: str
    embedder: str
    n: int
    severity_match: float
    component_match: float
    top1_retrieval_match: float
    top3_retrieval_match: float
    suggested_diff_parses: float
    mean_files_overlap: float
    cases: list[CaseScore]
    generated_at: str


def load_suite(path: Path) -> list[EvalCase]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=str(c["id"]),
            bug_report=str(c["bug_report"]),
            severity=str(c["severity"]),
            component=str(c["component"]),
            expected_top1_resolution_id=str(c["expected_top1_resolution_id"]),
            expected_files_changed=list(c.get("expected_files_changed", [])),
        )
        for c in data["cases"]
    ]


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def score_case(case: EvalCase, outcome: TriageOutcome) -> CaseScore:
    classification = outcome.classification.output
    retrieved_ids = [m.resolution_id for m in outcome.retrieved]
    return CaseScore(
        case_id=case.id,
        severity_match=classification.severity == case.severity,
        component_match=classification.component == case.component,
        top1_retrieval_match=bool(retrieved_ids)
        and retrieved_ids[0] == case.expected_top1_resolution_id,
        top3_retrieval_match=case.expected_top1_resolution_id in retrieved_ids[:3],
        suggested_diff_parses=outcome.suggestion.diff_parses,
        suggested_files_overlap=_jaccard(
            outcome.suggestion.output.applies_to_files, case.expected_files_changed
        ),
        retrieved_ids=retrieved_ids,
        classification=classification.model_dump(),
    )


def run_eval(
    *,
    suite_path: Path,
    provider: ChatProvider,
    embedder: Embedder,
    resolutions: list[Resolution],
    repo_root: Path,
) -> EvalReport:
    cases = load_suite(suite_path)
    scores: list[CaseScore] = []
    for case in cases:
        outcome = run_triage(
            provider=provider,
            embedder=embedder,
            resolutions=resolutions,
            bug_report=case.bug_report,
            repo_root=repo_root,
        )
        scores.append(score_case(case, outcome))
    n = len(scores) or 1

    def avg(getter: str) -> float:
        return round(sum(int(getattr(s, getter)) for s in scores) / n, 3)

    mean_overlap = round(sum(s.suggested_files_overlap for s in scores) / n, 3)
    return EvalReport(
        suite=suite_path.stem,
        provider=provider.name,
        embedder=type(embedder).__name__,
        n=n,
        severity_match=avg("severity_match"),
        component_match=avg("component_match"),
        top1_retrieval_match=avg("top1_retrieval_match"),
        top3_retrieval_match=avg("top3_retrieval_match"),
        suggested_diff_parses=avg("suggested_diff_parses"),
        mean_files_overlap=mean_overlap,
        cases=scores,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def report_to_dict(report: EvalReport) -> dict[str, Any]:
    return {
        "suite": report.suite,
        "provider": report.provider,
        "embedder": report.embedder,
        "n": report.n,
        "metrics": {
            "severity_match": report.severity_match,
            "component_match": report.component_match,
            "top1_retrieval_match": report.top1_retrieval_match,
            "top3_retrieval_match": report.top3_retrieval_match,
            "suggested_diff_parses": report.suggested_diff_parses,
            "mean_files_overlap": report.mean_files_overlap,
        },
        "generated_at": report.generated_at,
        "cases": [
            {
                "case_id": s.case_id,
                "severity_match": s.severity_match,
                "component_match": s.component_match,
                "top1_retrieval_match": s.top1_retrieval_match,
                "top3_retrieval_match": s.top3_retrieval_match,
                "suggested_diff_parses": s.suggested_diff_parses,
                "suggested_files_overlap": s.suggested_files_overlap,
                "retrieved_ids": s.retrieved_ids,
                "classification": s.classification,
            }
            for s in report.cases
        ],
    }


def report_to_markdown(report: EvalReport) -> str:
    lines = [
        f"# {report.suite} eval — {report.provider} / {report.embedder}",
        "",
        f"Cases: {report.n}    Generated: {report.generated_at}",
        "",
        "| metric | score |",
        "| --- | --- |",
        f"| severity_match | {report.severity_match} |",
        f"| component_match | {report.component_match} |",
        f"| top1_retrieval_match | {report.top1_retrieval_match} |",
        f"| top3_retrieval_match | {report.top3_retrieval_match} |",
        f"| suggested_diff_parses | {report.suggested_diff_parses} |",
        f"| mean_files_overlap | {report.mean_files_overlap} |",
    ]
    return "\n".join(lines) + "\n"


def write_report(report: EvalReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report_to_dict(report), indent=2) + "\n", encoding="utf-8")


def build_default_runtime(
    provider_name: str | None = None, *, prefer_hash: bool = True
) -> tuple[ChatProvider, Embedder]:
    return build_provider(provider_name), build_embedder(prefer_hash=prefer_hash)
