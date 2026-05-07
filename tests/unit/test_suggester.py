"""Suggester: diff-parse gate + JSON robustness."""

from __future__ import annotations

import json
from pathlib import Path

from bug_triage.classifier import ClassifierOutput, ClassifierResult
from bug_triage.providers.base import ChatMessage, ChatResponse
from bug_triage.providers.fake import FakeProvider
from bug_triage.retriever import ResolutionMatch
from bug_triage.suggester import suggest


def _classifier_result() -> ClassifierResult:
    return ClassifierResult(
        output=ClassifierOutput(severity="high", component="core", confidence=0.8, reasoning="x"),
        raw_response="{}",
        model_version="fake-1.0",
        prompt_version="2026.05.01",
        low_confidence=False,
    )


def _retrieved() -> list[ResolutionMatch]:
    return [
        ResolutionMatch(
            resolution_id="R001",
            similarity=0.9,
            severity="high",
            component="core",
            bug_report="div by zero",
            root_cause="missing guard",
            fix_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
            files_changed=["corpus/target/src/main/java/com/example/calc/Calculator.java"],
        ),
    ]


class _BadJsonProvider:
    name = "bad"

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:
        return ChatResponse(
            text="not json {{", tokens_in=0, tokens_out=0, cost_usd=0.0, model_version="bad-1"
        )


class _BadDiffProvider:
    name = "baddiff"

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:
        payload = {
            "suggested_diff": "this is not a unified diff at all",
            "rationale": "x",
            "confidence": 0.9,
            "applies_to_files": ["a"],
            "based_on_resolutions": ["R001"],
        }
        return ChatResponse(
            text=json.dumps(payload),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            model_version="baddiff-1",
        )


def test_fake_provider_emits_parseable_diff(tmp_path: Path) -> None:
    result = suggest(
        FakeProvider(),
        "Calculator.div returns Infinity for zero divisor",
        _classifier_result(),
        _retrieved(),
        repo_root=tmp_path,
    )
    assert result.diff_parses is True
    assert result.parse_error is None
    assert "based_on_resolutions" in result.output.model_dump()
    assert result.output.confidence > 0.0


def test_invalid_json_yields_zero_confidence(tmp_path: Path) -> None:
    result = suggest(
        _BadJsonProvider(),
        "any",
        _classifier_result(),
        _retrieved(),
        repo_root=tmp_path,
    )
    assert result.diff_parses is False
    assert result.output.confidence == 0.0


def test_invalid_diff_zeros_confidence(tmp_path: Path) -> None:
    result = suggest(
        _BadDiffProvider(),
        "any",
        _classifier_result(),
        _retrieved(),
        repo_root=tmp_path,
    )
    assert result.diff_parses is False
    assert result.parse_error is not None
    assert result.output.confidence == 0.0
