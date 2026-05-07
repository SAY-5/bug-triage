"""Smoke test: clone corpus/target/, apply a diff, run mvn verify.

Walks 3 hand-picked resolutions through the apply-and-test loop. Used by the
``apply-and-test-smoke`` CI job. Exits non-zero if any of them fail to clone
or to invoke mvn (apply success isn't required -- the synthetic diffs in the
hand-written corpus reference now-fixed code, so they may not apply cleanly).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from bug_triage.applier import (
    ApplyResult,
    TestResult,
    apply_diff,
    clone_target,
    run_tests,
)
from bug_triage.corpus import iter_resolution_files

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = REPO_ROOT / "corpus" / "target"

# Three hand-picked resolutions for the smoke. R001 is the canonical
# division-by-zero exemplar; R006 is null-input handling in the parser;
# R005 is the AtomicLong refactor for the invocations counter.
SMOKE_IDS = ("R001", "R005", "R006")


def _load(rid: str) -> dict[str, object]:
    for path in iter_resolution_files(REPO_ROOT / "corpus" / "resolutions"):
        if path.stem == rid:
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit(f"resolution {rid} not found")


def _smoke_one(rid: str) -> tuple[ApplyResult, TestResult]:
    data = _load(rid)
    diff = str(data["fix_diff"])
    with tempfile.TemporaryDirectory(prefix=f"smoke-{rid}-") as tmp:
        clone = clone_target(TARGET_DIR, Path(tmp) / "clone")
        apply_result = apply_diff(diff, clone)
        if not apply_result.success:
            test_result = TestResult(
                build_success=False,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                skipped=apply_result.skipped,
                reason=apply_result.reason or "diff did not apply",
            )
        else:
            test_result = run_tests(clone)
    return apply_result, test_result


def main() -> int:
    if shutil.which("mvn") is None:
        print("mvn not available; smoke skipped", file=sys.stderr)
        return 0
    summary: list[dict[str, object]] = []
    any_clone_failure = False
    for rid in SMOKE_IDS:
        apply_result, test_result = _smoke_one(rid)
        if test_result.skipped and test_result.reason == "mvn not on PATH":
            any_clone_failure = True
        summary.append(
            {
                "resolution_id": rid,
                "apply_success": apply_result.success,
                "hunks_applied": apply_result.hunks_applied,
                "hunks_rejected": apply_result.hunks_rejected,
                "build_success": test_result.build_success,
                "tests_run": test_result.tests_run,
                "tests_passed": test_result.tests_passed,
                "tests_failed": test_result.tests_failed,
            }
        )
    print(json.dumps({"smoke": summary}, indent=2))
    return 1 if any_clone_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
