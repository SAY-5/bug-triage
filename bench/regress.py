"""Bench-regress gate.

Runs the bench harness, compares against ``bench/baseline.json``, and exits
non-zero if any of these regress beyond the configured tolerances:

  - top-1 retrieval rate drops by > 0.05 (absolute)
  - top-3 retrieval rate drops by > 0.05 (absolute)
  - P95 latency grows by > 100% over the baseline (caps absolute spikes)

The first run of the gate (no baseline file) writes the current result as the
baseline and exits 0; subsequent runs compare against it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from bench.harness import REPO_ROOT, BenchResult, run, write_results

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

TOP1_TOLERANCE = 0.05
TOP3_TOLERANCE = 0.05
LATENCY_RATIO = 2.0  # current must not exceed 2x baseline P95


@dataclass(frozen=True)
class RegressionVerdict:
    ok: bool
    reasons: list[str]


def _load_baseline(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compare(current: BenchResult, baseline: dict[str, float]) -> RegressionVerdict:
    reasons: list[str] = []
    if current.top_1_rate + TOP1_TOLERANCE < float(baseline["top_1_rate"]):
        reasons.append(
            f"top_1_rate regressed: {current.top_1_rate} < {baseline['top_1_rate']} - {TOP1_TOLERANCE}"
        )
    if current.top_3_rate + TOP3_TOLERANCE < float(baseline["top_3_rate"]):
        reasons.append(
            f"top_3_rate regressed: {current.top_3_rate} < {baseline['top_3_rate']} - {TOP3_TOLERANCE}"
        )
    base_p95 = float(baseline["latency_p95_ms"])
    if base_p95 > 0 and current.latency_p95_ms > LATENCY_RATIO * base_p95:
        reasons.append(
            f"latency_p95_ms regressed: {current.latency_p95_ms} > {LATENCY_RATIO}x {base_p95}"
        )
    return RegressionVerdict(ok=not reasons, reasons=reasons)


def main() -> int:
    result = run()
    write_results(result)
    baseline = _load_baseline(BASELINE_PATH)
    if baseline is None:
        BASELINE_PATH.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        try:
            display = str(BASELINE_PATH.relative_to(REPO_ROOT))
        except ValueError:
            display = str(BASELINE_PATH)
        print(f"no baseline; wrote {display}")
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    verdict = compare(result, baseline)
    print(json.dumps(result.to_dict(), indent=2))
    if not verdict.ok:
        for reason in verdict.reasons:
            print(f"REGRESSION: {reason}", file=sys.stderr)
        return 1
    print("bench-regress: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
