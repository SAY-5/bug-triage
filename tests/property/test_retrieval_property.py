"""Hypothesis property tests for retriever.

Properties verified:
- top_1 always has the highest similarity in the returned list (descending order)
- the descending-similarity invariant holds for any k
- when the query exactly matches one corpus row, that row is returned at top-1
- the number of returned matches is min(k, |corpus|)
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bug_triage.embedder import EMBED_DIM, HashEmbedder
from bug_triage.models import Resolution
from bug_triage.retriever import cosine_similarity, retrieve_in_memory

_HC = [
    HealthCheck.too_slow,
    HealthCheck.large_base_example,
    HealthCheck.data_too_large,
]


def _embedding_strategy() -> st.SearchStrategy[list[float]]:
    return st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=EMBED_DIM,
        max_size=EMBED_DIM,
    )


def _make_resolution(rid: str, embedding: list[float]) -> Resolution:
    return Resolution(
        id=rid,
        bug_report=f"bug {rid}",
        root_cause=f"cause {rid}",
        fix_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=["x"],
        severity="medium",
        component="core",
        resolved_at=datetime(2026, 1, 1, tzinfo=UTC),
        embedding=embedding,
    )


@given(
    embeddings=st.lists(_embedding_strategy(), min_size=1, max_size=15),
    k=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=80, deadline=None, suppress_health_check=_HC)
def test_topk_returns_descending_similarity(embeddings: list[list[float]], k: int) -> None:
    """top-k results must be in descending similarity order."""
    embedder = HashEmbedder()
    rows = [_make_resolution(f"R{i:03d}", emb) for i, emb in enumerate(embeddings)]
    matches = retrieve_in_memory(rows, embedder, "arbitrary query text", k=k)

    assert len(matches) == min(k, len(embeddings))
    sims = [m.similarity for m in matches]
    assert sims == sorted(sims, reverse=True)


@given(
    embeddings=st.lists(_embedding_strategy(), min_size=2, max_size=15),
    k=st.integers(min_value=2, max_value=10),
)
@settings(max_examples=80, deadline=None, suppress_health_check=_HC)
def test_top1_has_max_similarity(embeddings: list[list[float]], k: int) -> None:
    """top_1 must have a similarity >= every other returned match."""
    embedder = HashEmbedder()
    rows = [_make_resolution(f"R{i:03d}", emb) for i, emb in enumerate(embeddings)]
    matches = retrieve_in_memory(rows, embedder, "arbitrary query text", k=k)
    if not matches:
        return
    top1 = matches[0]
    for m in matches[1:]:
        assert top1.similarity >= m.similarity


@given(
    queries=st.lists(
        st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=1, max_size=80
        ),
        min_size=2,
        max_size=10,
        unique=True,
    )
)
@settings(max_examples=40, deadline=None, suppress_health_check=_HC)
def test_exact_match_query_lands_at_top1(queries: list[str]) -> None:
    """When the incoming bug report is byte-for-byte one of the corpus reports,
    retrieve_in_memory must rank that resolution at top-1 (its self-cosine is 1.0)."""
    embedder = HashEmbedder()
    rows: list[Resolution] = []
    for i, q in enumerate(queries):
        rows.append(_make_resolution(f"R{i:03d}", embedder.embed(q)))
    target_idx = 0
    target_query = queries[target_idx]
    matches = retrieve_in_memory(rows, embedder, target_query, k=1)
    assert matches, "expected at least one match"
    # Embedded form of target_query must produce maximum cosine to its own row.
    assert matches[0].resolution_id == f"R{target_idx:03d}"


@given(
    a=_embedding_strategy(),
    b=_embedding_strategy(),
)
@settings(max_examples=80, deadline=None, suppress_health_check=_HC)
def test_cosine_is_bounded(a: list[float], b: list[float]) -> None:
    """cosine_similarity output must lie in [-1, 1] (or be 0 for zero-vectors)."""
    sim = cosine_similarity(a, b)
    # Floating point can push slightly outside [-1, 1]; allow a small epsilon.
    assert -1.0 - 1e-9 <= sim <= 1.0 + 1e-9
