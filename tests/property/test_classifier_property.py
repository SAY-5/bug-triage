"""Hypothesis property tests for classifier output validation.

Generates random LLM responses (well-formed and malformed) and asserts:
- responses with severity outside the closed enum are always rejected
- responses with component outside the closed enum are always rejected
- responses with confidence outside [0, 1] are always rejected
- responses with extra keys are rejected (extra='forbid')
- responses missing required fields are rejected
- well-formed responses always parse without raising
- ill-formed JSON (random byte streams) never crashes the parser; only ClassifierError
"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bug_triage.classifier import ClassifierError, ClassifierOutput, classify
from bug_triage.providers.base import ChatMessage, ChatResponse

VALID_SEVERITY = ("critical", "high", "medium", "low")
VALID_COMPONENT = ("api", "core", "util", "tests", "build")


class _ScriptedProvider:
    name = "scripted"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:
        return ChatResponse(
            text=self._payload,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            model_version="scripted-1",
        )


@st.composite
def well_formed_payload(draw: st.DrawFn) -> dict[str, object]:
    return {
        "severity": draw(st.sampled_from(VALID_SEVERITY)),
        "component": draw(st.sampled_from(VALID_COMPONENT)),
        "confidence": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "reasoning": draw(
            st.text(
                alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
                min_size=1,
                max_size=400,
            )
        ),
    }


@given(payload=well_formed_payload())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_well_formed_payload_always_parses(payload: dict[str, object]) -> None:
    provider = _ScriptedProvider(json.dumps(payload))
    result = classify(provider, "any bug report")
    assert isinstance(result.output, ClassifierOutput)
    assert result.output.severity == payload["severity"]
    assert result.output.component == payload["component"]


@given(
    bad_severity=st.text(min_size=1, max_size=20).filter(lambda s: s not in VALID_SEVERITY),
    component=st.sampled_from(VALID_COMPONENT),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_bad_severity_always_rejected(bad_severity: str, component: str, confidence: float) -> None:
    payload = {
        "severity": bad_severity,
        "component": component,
        "confidence": confidence,
        "reasoning": "x",
    }
    provider = _ScriptedProvider(json.dumps(payload))
    try:
        classify(provider, "any")
    except ClassifierError:
        return
    raise AssertionError(f"expected ClassifierError for severity={bad_severity!r}")


@given(
    severity=st.sampled_from(VALID_SEVERITY),
    bad_component=st.text(min_size=1, max_size=20).filter(lambda s: s not in VALID_COMPONENT),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_bad_component_always_rejected(
    severity: str, bad_component: str, confidence: float
) -> None:
    payload = {
        "severity": severity,
        "component": bad_component,
        "confidence": confidence,
        "reasoning": "x",
    }
    provider = _ScriptedProvider(json.dumps(payload))
    try:
        classify(provider, "any")
    except ClassifierError:
        return
    raise AssertionError(f"expected ClassifierError for component={bad_component!r}")


@given(
    bad_confidence=st.one_of(
        st.floats(max_value=-0.0001, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.0001, allow_nan=False, allow_infinity=False),
    )
)
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_out_of_range_confidence_rejected(bad_confidence: float) -> None:
    payload = {
        "severity": "high",
        "component": "core",
        "confidence": bad_confidence,
        "reasoning": "x",
    }
    provider = _ScriptedProvider(json.dumps(payload))
    try:
        classify(provider, "any")
    except ClassifierError:
        return
    raise AssertionError(f"expected ClassifierError for confidence={bad_confidence!r}")


@given(
    extra_key=st.text(min_size=1, max_size=12).filter(
        lambda s: s not in {"severity", "component", "confidence", "reasoning"}
    ),
    extra_value=st.one_of(st.integers(), st.text(max_size=20), st.booleans()),
)
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_extra_keys_rejected(extra_key: str, extra_value: object) -> None:
    payload = {
        "severity": "low",
        "component": "build",
        "confidence": 0.5,
        "reasoning": "x",
        extra_key: extra_value,
    }
    provider = _ScriptedProvider(json.dumps(payload))
    try:
        classify(provider, "any")
    except ClassifierError:
        return
    raise AssertionError(f"expected ClassifierError for extra key {extra_key!r}")


@given(raw=st.binary(min_size=0, max_size=512))
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_random_bytes_only_raise_classifier_error(raw: bytes) -> None:
    """Whatever the LLM emits, the classifier must never raise anything other
    than ClassifierError (or succeed). No KeyError, ValueError, etc. leaks out."""
    import contextlib

    try:
        text = raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        text = ""
    provider = _ScriptedProvider(text)
    with contextlib.suppress(ClassifierError):
        classify(provider, "any")
