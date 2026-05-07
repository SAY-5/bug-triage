"""Classifier output validation: closed enums + JSON robustness."""

from __future__ import annotations

import json

import pytest

from bug_triage.classifier import ClassifierError, ClassifierOutput, classify
from bug_triage.providers.base import ChatMessage, ChatResponse
from bug_triage.providers.fake import FakeProvider


class _ScriptedProvider:
    name = "scripted"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:
        return ChatResponse(
            text=self._payload, tokens_in=0, tokens_out=0, cost_usd=0.0, model_version="scripted-1"
        )


def test_fake_provider_returns_structured_classification() -> None:
    provider = FakeProvider()
    result = classify(provider, "Calculator.div returns Infinity for zero divisor at /div endpoint")
    assert isinstance(result.output, ClassifierOutput)
    assert result.output.severity in {"critical", "high", "medium", "low"}
    assert result.output.component in {"api", "core", "util", "tests", "build"}
    assert 0.0 <= result.output.confidence <= 1.0


def test_rejects_out_of_enum_severity() -> None:
    provider = _ScriptedProvider(
        json.dumps(
            {"severity": "blocker", "component": "api", "confidence": 0.7, "reasoning": "bad"}
        )
    )
    with pytest.raises(ClassifierError):
        classify(provider, "anything")


def test_rejects_invalid_json() -> None:
    provider = _ScriptedProvider("not-json {")
    with pytest.raises(ClassifierError):
        classify(provider, "anything")


def test_rejects_extra_keys() -> None:
    payload = {
        "severity": "high",
        "component": "core",
        "confidence": 0.7,
        "reasoning": "ok",
        "extra": "nope",
    }
    provider = _ScriptedProvider(json.dumps(payload))
    with pytest.raises(ClassifierError):
        classify(provider, "anything")


def test_low_confidence_flag() -> None:
    provider = _ScriptedProvider(
        json.dumps({"severity": "low", "component": "api", "confidence": 0.3, "reasoning": "weak"})
    )
    result = classify(provider, "anything")
    assert result.low_confidence is True
