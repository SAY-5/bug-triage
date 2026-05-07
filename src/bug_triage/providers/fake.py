"""Deterministic FakeProvider plus a factory that picks the right backend.

FakeProvider inspects the prompt, detects whether it's a classification or a
suggestion call, and emits a structured JSON payload. Keyword heuristics map
realistic bug reports to plausible (severity, component, resolution_id)
triples so the eval suite has a deterministic, hermetic ground truth without
real LLM calls.
"""

from __future__ import annotations

import json
import os
import re

from bug_triage.providers.base import ChatMessage, ChatResponse

# --- Heuristics ------------------------------------------------------------

_SEVERITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "critical": (
        "crash",
        "segfault",
        "outage",
        "data loss",
        "data corruption",
        "deadlock",
        "production down",
    ),
    "high": (
        "stack trace",
        "exception",
        "npe",
        "nullpointer",
        "division by zero",
        "overflow",
        "race",
        "concurrent",
        "incorrect result",
        "wrong answer",
    ),
    "medium": (
        "validation",
        "invalid input",
        "bad request",
        "config",
        "default",
        "edge case",
        "off-by-one",
    ),
    "low": (
        "typo",
        "documentation",
        "log message",
        "cosmetic",
        "rename",
    ),
}

_COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "api": ("/add", "/sub", "/mul", "/div", "/eval", "endpoint", "http", "calcserver", "request"),
    "core": ("calculator", "arithmetic", "expression", "parser", "evaluate", "tokenize", "rpn"),
    "util": ("validation", "parseoperand", "requirenonempty", "operand"),
    "tests": ("test", "junit", "assertequals", "assertthrows"),
    "build": ("pom", "maven", "compiler", "release", "dependency"),
}


def classify_text(bug_report: str) -> tuple[str, str, float]:
    """Return ``(severity, component, confidence)`` for a bug report."""

    text = bug_report.lower()

    severity = "medium"
    severity_hits = 0
    for level, words in _SEVERITY_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > severity_hits:
            severity = level
            severity_hits = hits

    component = "core"
    component_hits = 0
    for name, words in _COMPONENT_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > component_hits:
            component = name
            component_hits = hits

    total = severity_hits + component_hits
    confidence = 0.55 + min(0.4, 0.05 * total)
    return severity, component, round(confidence, 3)


# --- Provider --------------------------------------------------------------


_CLASSIFY_MARK = "TASK: classify"
_SUGGEST_MARK = "TASK: suggest"


class FakeProvider:
    name = "fake"

    def __init__(self, model_version: str = "fake-1.0") -> None:
        self._model_version = model_version

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:
        joined = "\n".join(m.content for m in messages)
        if _CLASSIFY_MARK in joined:
            text = self._classify_response(joined)
        elif _SUGGEST_MARK in joined:
            text = self._suggest_response(joined)
        else:
            text = json.dumps({"error": "unknown task"})
        tokens_in = sum(len(m.content) for m in messages) // 4
        tokens_out = len(text) // 4
        return ChatResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
            model_version=self._model_version,
        )

    @staticmethod
    def _classify_response(prompt: str) -> str:
        bug_report = _extract_bug_report(prompt)
        severity, component, confidence = classify_text(bug_report)
        reasoning = (
            f"Heuristic classifier matched keywords for severity={severity} "
            f"and component={component}."
        )
        return json.dumps(
            {
                "severity": severity,
                "component": component,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        )

    @staticmethod
    def _suggest_response(prompt: str) -> str:
        ids = _extract_resolution_ids(prompt)
        files = _extract_files(prompt)
        head_id = ids[0] if ids else "R000"
        diff = _SCRIPTED_DIFFS.get(head_id, _DEFAULT_DIFF)
        rationale = (
            f"Top retrieved resolution {head_id} matches the failure mode; "
            f"applying the analogous guard. Confirms with parser semantics."
        )
        return json.dumps(
            {
                "suggested_diff": diff,
                "rationale": rationale,
                "confidence": 0.7,
                "applies_to_files": (
                    files[:2]
                    if files
                    else ["corpus/target/src/main/java/com/example/calc/Calculator.java"]
                ),
                "based_on_resolutions": ids[:3],
            }
        )


def _extract_bug_report(prompt: str) -> str:
    match = re.search(r"INCOMING_BUG_REPORT_BEGIN(.*?)INCOMING_BUG_REPORT_END", prompt, re.S)
    if not match:
        return prompt
    return match.group(1).strip()


def _extract_resolution_ids(prompt: str) -> list[str]:
    return re.findall(r"resolution_id=(R\d+)", prompt)


def _extract_files(prompt: str) -> list[str]:
    matches = re.findall(r"FILE_PATH=([^\n]+)", prompt)
    return [m.strip() for m in matches]


_DEFAULT_DIFF = """--- a/corpus/target/src/main/java/com/example/calc/Calculator.java
+++ b/corpus/target/src/main/java/com/example/calc/Calculator.java
@@ -1,2 +1,2 @@
 // suggester placeholder
-// before
+// after
"""


_SCRIPTED_DIFFS: dict[str, str] = {
    "R001": """--- a/corpus/target/src/main/java/com/example/calc/Calculator.java
+++ b/corpus/target/src/main/java/com/example/calc/Calculator.java
@@ -1,3 +1,6 @@
 public static double div(long a, long b) {
     INVOCATIONS.incrementAndGet();
+    if (b == 0L) {
+        throw new ArithmeticException(\"division by zero\");
+    }
     return (double) a / (double) b;
""",
}


# --- Factory ---------------------------------------------------------------


def build_provider(name: str | None = None) -> FakeProvider:
    """Return a provider instance.

    Today only ``fake`` is wired. Real providers are stubbed for BYOK; calling
    them without keys raises so misconfiguration is loud.
    """

    name = (name or os.environ.get("PROVIDER", "fake")).lower()
    if name == "fake":
        return FakeProvider()
    if name == "anthropic":
        from bug_triage.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()  # type: ignore[return-value]
    if name == "openai":
        from bug_triage.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()  # type: ignore[return-value]
    raise ValueError(f"unknown provider: {name}")
