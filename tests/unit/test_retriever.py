"""Retriever cosine math + in-memory top-k against synthetic vectors."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bug_triage.embedder import HashEmbedder
from bug_triage.models import Resolution
from bug_triage.retriever import cosine_similarity, retrieve_in_memory


def test_cosine_dimension_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


def test_cosine_zero_vector_returns_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_basic_values() -> None:
    assert math.isclose(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
    assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0)


def _resolution(rid: str, text: str, embedder: HashEmbedder) -> Resolution:
    return Resolution(
        id=rid,
        bug_report=text,
        root_cause=text,
        fix_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=["x"],
        severity="medium",
        component="core",
        resolved_at=datetime(2026, 1, 1, tzinfo=UTC),
        embedding=embedder.embed(text),
    )


def test_retrieve_in_memory_returns_topk_in_order() -> None:
    e = HashEmbedder()
    rows = [
        _resolution("R-near", "Calculator division by zero arithmetic exception", e),
        _resolution("R-mid", "ExpressionParser unbalanced parentheses guard", e),
        _resolution("R-far", "Maven Surefire JUnit platform discovery", e),
    ]
    matches = retrieve_in_memory(rows, e, "Calculator division by zero", k=2)
    assert [m.resolution_id for m in matches] == ["R-near", "R-mid"]
    assert matches[0].similarity >= matches[1].similarity
