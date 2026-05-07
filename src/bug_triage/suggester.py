"""Fix suggester: builds a prompt with retrieved exemplars + Java source files.

Validates the LLM output as JSON, then validates the diff parses with
``unidiff``. On parse failure we surface the malformed output and zero out
the confidence so downstream consumers can detect it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from unidiff import PatchSet

from bug_triage.classifier import ClassifierResult
from bug_triage.prompts import load as load_prompt
from bug_triage.providers.base import ChatMessage, ChatProvider
from bug_triage.retriever import ResolutionMatch

MAX_RETRIEVED_CHARS = 8000
MAX_FILE_CHARS = 4000


class SuggesterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_diff: str
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    applies_to_files: list[str] = Field(default_factory=list)
    based_on_resolutions: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class SuggestionResult:
    output: SuggesterOutput
    raw_response: str
    diff_parses: bool
    parse_error: str | None
    model_version: str
    prompt_version: str


def suggest(
    provider: ChatProvider,
    bug_report: str,
    classification: ClassifierResult,
    retrieved: Sequence[ResolutionMatch],
    *,
    repo_root: Path,
    model: str = "default",
) -> SuggestionResult:
    prompt = load_prompt("suggest")
    retrieved_block = _render_retrieved(retrieved)
    candidate_files = _candidate_files(retrieved)
    files_block = _render_files(candidate_files, repo_root)
    rendered = prompt.render(
        bug_report=bug_report,
        classification_json=json.dumps(classification.output.model_dump()),
        retrieved_block=retrieved_block,
        files_block=files_block,
    )
    response = provider.chat(
        [
            ChatMessage(role="system", content=prompt.system),
            ChatMessage(role="user", content=rendered),
        ],
        model=model,
    )
    output, raw = _parse_or_empty(response.text)
    diff_parses, parse_error = _validate_diff(output.suggested_diff)
    if not diff_parses:
        # Zero-out confidence so consumers know the diff is unusable.
        output = output.model_copy(update={"confidence": 0.0})
    return SuggestionResult(
        output=output,
        raw_response=raw,
        diff_parses=diff_parses,
        parse_error=parse_error,
        model_version=response.model_version,
        prompt_version=prompt.version,
    )


def _candidate_files(retrieved: Sequence[ResolutionMatch]) -> list[str]:
    seen: list[str] = []
    for r in retrieved:
        for f in r.files_changed:
            if f not in seen:
                seen.append(f)
    return seen


def _render_retrieved(retrieved: Sequence[ResolutionMatch]) -> str:
    chunks: list[str] = []
    used = 0
    for r in retrieved:
        block = (
            f"--- resolution_id={r.resolution_id} "
            f"severity={r.severity} component={r.component} "
            f"similarity={r.similarity:.3f} ---\n"
            f"BUG: {r.bug_report}\n"
            f"ROOT_CAUSE: {r.root_cause}\n"
            f"FILES: {', '.join(r.files_changed)}\n"
            f"FIX_DIFF:\n{r.fix_diff}\n"
        )
        if used + len(block) > MAX_RETRIEVED_CHARS:
            break
        chunks.append(block)
        used += len(block)
    return "\n".join(chunks) if chunks else "(no resolutions retrieved)"


def _render_files(paths: Sequence[str], repo_root: Path) -> str:
    chunks: list[str] = []
    for rel in paths:
        candidate = (repo_root / rel).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n...truncated...\n"
        chunks.append(f"FILE_PATH={rel}\n```\n{text}\n```")
    return "\n".join(chunks) if chunks else "(no source files attached)"


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _parse_or_empty(raw: str) -> tuple[SuggesterOutput, str]:
    candidate = raw.strip()
    fenced = _FENCED_JSON_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return _empty_output(), raw
    try:
        return SuggesterOutput.model_validate(payload), raw
    except ValidationError:
        return _empty_output(), raw


def _empty_output() -> SuggesterOutput:
    return SuggesterOutput(
        suggested_diff="",
        rationale="suggester output failed JSON validation; no fix produced.",
        confidence=0.0,
        applies_to_files=[],
        based_on_resolutions=[],
    )


def _validate_diff(diff_text: str) -> tuple[bool, str | None]:
    text = diff_text.strip()
    if not text:
        return False, "empty diff"
    try:
        patch = PatchSet(StringIO(text))
    except Exception as exc:  # noqa: BLE001 - unidiff raises various types
        return False, str(exc)
    if len(patch) == 0:
        return False, "diff parsed but contained no files"
    return True, None
