"""End-to-end triage pipeline. Used by the API, CLI, and eval harness."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bug_triage.classifier import ClassifierResult, classify
from bug_triage.embedder import Embedder
from bug_triage.models import Resolution
from bug_triage.providers.base import ChatProvider
from bug_triage.retriever import ResolutionMatch, retrieve_in_memory
from bug_triage.suggester import SuggestionResult, suggest


@dataclass(frozen=True)
class TriageOutcome:
    bug_report: str
    classification: ClassifierResult
    retrieved: list[ResolutionMatch]
    suggestion: SuggestionResult
    latency_ms: int


def run_triage(
    *,
    provider: ChatProvider,
    embedder: Embedder,
    resolutions: Sequence[Resolution],
    bug_report: str,
    repo_root: Path,
    k: int = 3,
) -> TriageOutcome:
    """Classify, retrieve, suggest -- in memory; no DB required."""

    started = time.perf_counter()
    classification = classify(provider, bug_report)
    matches = retrieve_in_memory(list(resolutions), embedder, bug_report, k=k)
    suggestion = suggest(
        provider,
        bug_report,
        classification,
        matches,
        repo_root=repo_root,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return TriageOutcome(
        bug_report=bug_report,
        classification=classification,
        retrieved=matches,
        suggestion=suggestion,
        latency_ms=latency_ms,
    )
