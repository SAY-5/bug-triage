"""Hash embedder determinism + dimensionality + cosine sanity."""

from __future__ import annotations

import math

from bug_triage.embedder import EMBED_DIM, HashEmbedder
from bug_triage.retriever import cosine_similarity


def test_dimension_is_384() -> None:
    e = HashEmbedder()
    assert e.dim == EMBED_DIM
    assert len(e.embed("hello world")) == EMBED_DIM


def test_deterministic() -> None:
    e = HashEmbedder()
    a = e.embed("Calculator.div should reject zero divisor")
    b = e.embed("Calculator.div should reject zero divisor")
    assert a == b


def test_l2_normalized() -> None:
    e = HashEmbedder()
    v = e.embed("foo bar baz")
    norm = math.sqrt(sum(x * x for x in v))
    assert math.isclose(norm, 1.0, rel_tol=1e-5)


def test_self_similarity_is_one() -> None:
    e = HashEmbedder()
    v = e.embed("ExpressionParser unbalanced parentheses")
    assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-5)


def test_overlap_yields_higher_similarity() -> None:
    e = HashEmbedder()
    base = e.embed("Calculator division by zero exception")
    near = e.embed("Calculator division by zero arithmetic error")
    far = e.embed("Maven Surefire JUnit platform discovery")
    assert cosine_similarity(base, near) > cosine_similarity(base, far)


def test_empty_input_zero_vector() -> None:
    v = HashEmbedder().embed("")
    assert all(x == 0.0 for x in v)
