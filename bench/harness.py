"""Bench harness: classify -> retrieve -> suggest over a fixed input set.

The harness loads the 200-resolution corpus, runs 50 incoming bug reports
through the pipeline, and emits a JSON results file with:

  - latency P50 and P95 (milliseconds, end-to-end)
  - top-1 retrieval rate
  - top-3 retrieval rate

Ground truth: each input is derived from one held-out corpus row by either
copying its bug report verbatim (50% of inputs) or by perturbing it (50%).
Top-k retrieval is "correct" iff that row appears in the top-k matches.

The harness is fully hermetic: FakeProvider, HashEmbedder, no network. A
fixed RNG seed makes the input set stable across runs.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import HashEmbedder
from bug_triage.models import Resolution
from bug_triage.pipeline import run_triage
from bug_triage.providers.fake import FakeProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "resolutions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

DEFAULT_BENCH_SEED = 0xC0FFEE
DEFAULT_NUM_INPUTS = 50


@dataclass(frozen=True)
class BenchInput:
    target_id: str
    query: str


@dataclass(frozen=True)
class BenchResult:
    timestamp: str
    corpus_size: int
    num_inputs: int
    top_1_rate: float
    top_3_rate: float
    latency_p50_ms: float
    latency_p95_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "corpus_size": self.corpus_size,
            "num_inputs": self.num_inputs,
            "top_1_rate": self.top_1_rate,
            "top_3_rate": self.top_3_rate,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
        }


def build_inputs(
    rows: list[Resolution],
    *,
    n: int = DEFAULT_NUM_INPUTS,
    seed: int = DEFAULT_BENCH_SEED,
) -> list[BenchInput]:
    """Pick ``n`` corpus rows and turn each into a BenchInput.

    Half the inputs reuse the row's bug_report verbatim. The other half append
    a deterministic suffix and trim a leading word so the embedder produces a
    *similar but not identical* vector. This lets us measure retrieval under
    paraphrase pressure rather than only on exact matches.
    """

    rng = random.Random(seed)
    if n > len(rows):
        n = len(rows)
    chosen = rng.sample(rows, n)
    inputs: list[BenchInput] = []
    for i, r in enumerate(chosen):
        if i % 2 == 0:
            query = r.bug_report
        else:
            words = r.bug_report.split()
            stripped = " ".join(words[1:]) if len(words) > 1 else r.bug_report
            query = f"observed in production: {stripped}"
        inputs.append(BenchInput(target_id=r.id, query=query))
    return inputs


def run(
    *,
    num_inputs: int = DEFAULT_NUM_INPUTS,
    seed: int = DEFAULT_BENCH_SEED,
    corpus_dir: Path | None = None,
) -> BenchResult:
    """Run the bench end-to-end and return aggregated metrics."""

    corpus_dir = corpus_dir or CORPUS_DIR
    rows = load_resolutions(corpus_dir)
    embedder = HashEmbedder()
    embed_resolutions(rows, embedder)
    provider = FakeProvider()

    inputs = build_inputs(rows, n=num_inputs, seed=seed)

    latencies: list[float] = []
    top1_hits = 0
    top3_hits = 0
    for inp in inputs:
        started = time.perf_counter()
        outcome = run_triage(
            provider=provider,
            embedder=embedder,
            resolutions=rows,
            bug_report=inp.query,
            repo_root=REPO_ROOT,
            k=3,
        )
        latencies.append((time.perf_counter() - started) * 1000.0)
        match_ids = [m.resolution_id for m in outcome.retrieved]
        if match_ids and match_ids[0] == inp.target_id:
            top1_hits += 1
        if inp.target_id in match_ids:
            top3_hits += 1

    n = len(inputs)
    top_1_rate = top1_hits / n if n else 0.0
    top_3_rate = top3_hits / n if n else 0.0
    p50 = statistics.median(latencies) if latencies else 0.0
    if latencies:
        sorted_ms = sorted(latencies)
        idx = max(0, int(round(0.95 * (len(sorted_ms) - 1))))
        p95 = sorted_ms[idx]
    else:
        p95 = 0.0

    return BenchResult(
        timestamp=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        corpus_size=len(rows),
        num_inputs=n,
        top_1_rate=round(top_1_rate, 4),
        top_3_rate=round(top_3_rate, 4),
        latency_p50_ms=round(p50, 3),
        latency_p95_ms=round(p95, 3),
    )


def write_results(result: BenchResult, *, out_dir: Path | None = None) -> Path:
    """Persist the bench result as JSON under ``bench/results/<timestamp>.json``."""

    out_dir = out_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.timestamp}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    result = run()
    path = write_results(result)
    print(json.dumps(result.to_dict(), indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
