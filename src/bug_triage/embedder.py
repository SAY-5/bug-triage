"""Embedder protocol plus a deterministic hash-based fallback.

The hash embedder produces 384-dimensional vectors derived from token-level
SHA-256 digests. It's not semantically meaningful, but it's deterministic,
fast, and good enough for hermetic CI: identical text yields identical
vectors, and small lexical overlaps produce non-trivial cosine similarity.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

import numpy as np

EMBED_DIM = 384


@runtime_checkable
class Embedder(Protocol):
    """A text embedder. ``dim`` is the fixed output dimensionality."""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class HashEmbedder:
    """Deterministic 384-d embedder for hermetic CI.

    For each token we hash to two 32-bit integers: one selects a slot in
    ``[0, dim)``, the other its sign. This is a signed feature-hashing
    embedder (a la the hashing trick) followed by L2 normalization so cosine
    similarity is well-behaved.
    """

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = np.zeros(self._dim, dtype=np.float32)
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return [float(x) for x in vec.tolist()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[slot] += sign
        norm = float(np.linalg.norm(vec))
        if norm == 0.0 or math.isnan(norm):
            return [float(x) for x in vec.tolist()]
        return [float(x) for x in (vec / norm).tolist()]


class SentenceTransformersEmbedder:
    """Wraps ``sentence-transformers/all-MiniLM-L6-v2`` (384-d).

    Imported lazily so the dependency stays optional. Falls back to
    ``HashEmbedder`` if the model can't load.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vector]


def build_embedder(*, prefer_hash: bool = False) -> Embedder:
    """Pick an embedder based on env preference and import availability."""

    if prefer_hash:
        return HashEmbedder()
    try:
        return SentenceTransformersEmbedder()
    except Exception:  # noqa: BLE001 - any import / load failure falls back
        return HashEmbedder()
