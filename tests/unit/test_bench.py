"""Bench harness + regress gate sanity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bench import harness, regress
from bench.harness import BenchInput, BenchResult


def test_build_inputs_count_matches_request() -> None:
    rows = harness.load_resolutions(harness.CORPUS_DIR)
    embedder = harness.HashEmbedder()
    harness.embed_resolutions(rows, embedder)
    inputs = harness.build_inputs(rows, n=20, seed=1)
    assert len(inputs) == 20
    assert all(isinstance(i, BenchInput) for i in inputs)


def test_run_emits_metrics_within_bounds() -> None:
    result = harness.run(num_inputs=15, seed=42)
    assert result.corpus_size >= 200
    assert result.num_inputs == 15
    assert 0.0 <= result.top_1_rate <= 1.0
    assert 0.0 <= result.top_3_rate <= 1.0
    assert result.top_3_rate >= result.top_1_rate
    assert result.latency_p95_ms >= result.latency_p50_ms
    assert result.latency_p50_ms >= 0.0


def test_write_results_creates_file(tmp_path: Path) -> None:
    result = harness.run(num_inputs=5, seed=7)
    path = harness.write_results(result, out_dir=tmp_path)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["num_inputs"] == 5


def _stub_result() -> BenchResult:
    return BenchResult(
        timestamp="20260101T000000Z",
        corpus_size=200,
        num_inputs=50,
        top_1_rate=0.7,
        top_3_rate=0.94,
        latency_p50_ms=10.0,
        latency_p95_ms=12.0,
    )


def test_compare_passes_when_metrics_steady() -> None:
    baseline = _stub_result().to_dict()
    verdict = regress.compare(_stub_result(), baseline)
    assert verdict.ok and verdict.reasons == []


def test_compare_flags_top1_regression() -> None:
    current = _stub_result()
    baseline = current.to_dict()
    regressed = BenchResult(**{**current.to_dict(), "top_1_rate": 0.5})
    verdict = regress.compare(regressed, baseline)
    assert not verdict.ok
    assert any("top_1_rate" in r for r in verdict.reasons)


def test_compare_flags_latency_regression() -> None:
    current = _stub_result()
    baseline = current.to_dict()
    slow = BenchResult(**{**current.to_dict(), "latency_p95_ms": 50.0})
    verdict = regress.compare(slow, baseline)
    assert not verdict.ok
    assert any("latency_p95_ms" in r for r in verdict.reasons)


def test_compare_flags_top3_regression() -> None:
    current = _stub_result()
    baseline = current.to_dict()
    regressed = BenchResult(**{**current.to_dict(), "top_3_rate": 0.5})
    verdict = regress.compare(regressed, baseline)
    assert not verdict.ok
    assert any("top_3_rate" in r for r in verdict.reasons)


def test_main_writes_baseline_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """First-run path: no baseline file -> exit 0 + write baseline."""

    fake_baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(regress, "BASELINE_PATH", fake_baseline)
    monkeypatch.setattr(harness, "RESULTS_DIR", tmp_path / "results")
    rc = regress.main()
    assert rc == 0
    assert fake_baseline.exists()
