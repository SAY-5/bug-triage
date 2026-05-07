"""Severity + component classifier with closed-enum validation.

The LLM may produce any string; we reject anything that doesn't parse as JSON
or contains values outside the closed enums. The Pydantic schema does the
heavy lifting -- a `ValidationError` here means the prompt+LLM combination
violated the contract and should be fixed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bug_triage.prompts import load as load_prompt
from bug_triage.providers.base import ChatMessage, ChatProvider, ChatResponse

Severity = Literal["critical", "high", "medium", "low"]
Component = Literal["api", "core", "util", "tests", "build"]


class ClassifierOutput(BaseModel):
    """Structured classifier output. Closed enums enforced by Pydantic."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    component: Component
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class ClassifierResult:
    output: ClassifierOutput
    raw_response: str
    model_version: str
    prompt_version: str
    low_confidence: bool


class ClassifierError(RuntimeError):
    """Raised when the provider response cannot be parsed/validated."""


def classify(
    provider: ChatProvider, bug_report: str, *, model: str = "default"
) -> ClassifierResult:
    """Run the classifier prompt and validate the structured output."""

    prompt = load_prompt("classify")
    rendered = prompt.render(bug_report=bug_report)
    response: ChatResponse = provider.chat(
        [
            ChatMessage(role="system", content=prompt.system),
            ChatMessage(role="user", content=rendered),
        ],
        model=model,
    )
    output = _parse(response.text)
    return ClassifierResult(
        output=output,
        raw_response=response.text,
        model_version=response.model_version,
        prompt_version=prompt.version,
        low_confidence=output.confidence < 0.5,
    )


def _parse(raw: str) -> ClassifierOutput:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClassifierError(f"classifier output is not valid JSON: {raw!r}") from exc
    try:
        return ClassifierOutput.model_validate(payload)
    except ValidationError as exc:
        raise ClassifierError(f"classifier output failed validation: {exc}") from exc
