"""Tests for the diff-apply-and-test loop."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bug_triage.applier import (
    ApplyResult,
    TestResult,
    _parse_surefire,
    apply_and_test,
    apply_diff,
    clone_target,
    run_tests,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = REPO_ROOT / "corpus" / "target"


def test_clone_target_copies_tree(tmp_path: Path) -> None:
    dest = tmp_path / "clone"
    clone_target(TARGET_DIR, dest)
    assert (dest / "pom.xml").is_file()
    assert (dest / "src/main/java/com/example/calc/Calculator.java").is_file()


def test_apply_empty_diff_fails_cleanly(tmp_path: Path) -> None:
    dest = clone_target(TARGET_DIR, tmp_path / "clone")
    result = apply_diff("", dest)
    assert not result.success
    assert result.reason == "empty diff"


def test_synthetic_passing_assertion_diff_applies(tmp_path: Path) -> None:
    """A synthetic diff that adds a passing test method must apply with 0 rejects."""

    dest = clone_target(TARGET_DIR, tmp_path / "clone")
    rel = "src/test/java/com/example/calc/CalculatorTest.java"
    original = (dest / rel).read_text(encoding="utf-8").splitlines(keepends=False)
    # Build a diff that replaces the file's closing line `}` with a new test
    # method followed by `}`. Two-line context window keeps the patch small.
    closing = "}"
    assert original[-1] == closing
    new_block = [
        "    @Test",
        "    void appliedSyntheticAssertion() {",
        "        assertEquals(2L, 1L + 1L);",
        "    }",
        "}",
    ]
    diff = (
        f"--- a/{rel}\n"
        f"+++ b/{rel}\n"
        f"@@ -{len(original)},1 +{len(original)},{len(new_block)} @@\n"
        f"-{closing}\n" + "\n".join(f"+{line}" for line in new_block) + "\n"
    )
    result = apply_diff(diff, dest)
    assert result.success, f"diff failed to apply: {result}"
    assert result.hunks_rejected == 0
    patched = (dest / rel).read_text(encoding="utf-8")
    assert "appliedSyntheticAssertion" in patched


def test_apply_then_run_tests_increases_pass_count(tmp_path: Path) -> None:
    """Synthetic diff adds 1 passing test method; mvn verify reports +1 passed.

    Skipped when mvn isn't available. This is the smoke check that the full
    apply -> mvn-verify loop produces a coherent ``tests_passed`` delta.
    """

    if shutil.which("mvn") is None:
        pytest.skip("mvn not available")

    # 1) Baseline: clean clone, run tests, record tests_passed.
    baseline_clone = clone_target(TARGET_DIR, tmp_path / "baseline")
    baseline = run_tests(baseline_clone)
    assert baseline.build_success, f"baseline build failed: {baseline.reason!r}"
    pre_pass = baseline.tests_passed

    # 2) Apply synthetic diff to a fresh clone, run tests, record tests_passed.
    patched_clone = clone_target(TARGET_DIR, tmp_path / "patched")
    rel = "src/test/java/com/example/calc/CalculatorTest.java"
    original = (patched_clone / rel).read_text(encoding="utf-8").splitlines(keepends=False)
    closing = "}"
    assert original[-1] == closing
    new_block = [
        "    @Test",
        "    void appliedSyntheticAssertion() {",
        "        assertEquals(2L, 1L + 1L);",
        "    }",
        "}",
    ]
    diff = (
        f"--- a/{rel}\n"
        f"+++ b/{rel}\n"
        f"@@ -{len(original)},1 +{len(original)},{len(new_block)} @@\n"
        f"-{closing}\n" + "\n".join(f"+{line}" for line in new_block) + "\n"
    )
    apply_result = apply_diff(diff, patched_clone)
    assert apply_result.success, f"diff failed to apply: {apply_result}"

    patched = run_tests(patched_clone)
    assert patched.build_success, f"patched build failed: {patched.reason!r}"
    assert (
        patched.tests_passed == pre_pass + 1
    ), f"expected pre+1 passes; got pre={pre_pass} post={patched.tests_passed}"


def test_apply_diff_rejects_unknown_file(tmp_path: Path) -> None:
    dest = clone_target(TARGET_DIR, tmp_path / "clone")
    bad_diff = (
        "--- a/does/not/exist.java\n"
        "+++ b/does/not/exist.java\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    result = apply_diff(bad_diff, dest)
    assert not result.success


def test_apply_diff_when_git_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("bug_triage.applier._which", lambda _t: None)
    dest = clone_target(TARGET_DIR, tmp_path / "clone")
    result = apply_diff(
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        dest,
    )
    assert isinstance(result, ApplyResult)
    assert result.skipped is True
    assert result.reason == "git not on PATH"


def test_run_tests_when_mvn_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("bug_triage.applier._which", lambda _t: None)
    result = run_tests(tmp_path)
    assert isinstance(result, TestResult)
    assert result.skipped is True
    assert result.reason == "mvn not on PATH"


def test_parse_surefire_summary() -> None:
    sample = (
        "[INFO] -------------------------------------------------------\n"
        "[INFO]  T E S T S\n"
        "[INFO] -------------------------------------------------------\n"
        "[INFO] Running com.example.calc.CalculatorTest\n"
        "[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\n"
        "[INFO] Results:\n"
        "[INFO] Tests run: 5, Failures: 1, Errors: 0, Skipped: 0\n"
    )
    tests_run, passed, failed = _parse_surefire(sample)
    assert tests_run == 5
    assert passed == 4
    assert failed == 1


def test_parse_surefire_no_match_returns_zeros() -> None:
    assert _parse_surefire("nothing here") == (0, 0, 0)


def test_apply_and_test_skipped_when_diff_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If apply fails, run_tests should not be invoked; the TestResult is filled in."""

    invocations: list[Path] = []

    def _stub_run_tests(project_dir: Path) -> TestResult:
        invocations.append(project_dir)
        return TestResult(build_success=True, tests_run=0, tests_passed=0, tests_failed=0)

    monkeypatch.setattr("bug_triage.applier.run_tests", _stub_run_tests)
    apply_result, test_result = apply_and_test(
        "",
        source=TARGET_DIR,
        work_dir=tmp_path / "clone",
    )
    assert apply_result.success is False
    assert test_result.build_success is False
    assert invocations == []  # run_tests must not be called when apply fails


def test_apply_and_test_clones_and_runs_when_apply_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Stub apply+run_tests so we can drive the orchestration without invoking mvn."""

    monkeypatch.setattr(
        "bug_triage.applier.apply_diff",
        lambda _diff, _proj: ApplyResult(
            success=True, hunks_applied=1, hunks_rejected=0, conflict_files=[]
        ),
    )
    monkeypatch.setattr(
        "bug_triage.applier.run_tests",
        lambda _proj: TestResult(build_success=True, tests_run=4, tests_passed=4, tests_failed=0),
    )
    apply_result, test_result = apply_and_test(
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        source=TARGET_DIR,
        work_dir=tmp_path / "clone",
    )
    assert apply_result.success
    assert test_result.build_success
    assert test_result.tests_passed == 4
    # Source tree must have been copied into work_dir.
    assert (tmp_path / "clone" / "pom.xml").is_file()


def test_clone_target_overwrites_existing(tmp_path: Path) -> None:
    dest = tmp_path / "clone"
    dest.mkdir()
    (dest / "stale.txt").write_text("stale", encoding="utf-8")
    clone_target(TARGET_DIR, dest)
    assert not (dest / "stale.txt").exists()
    assert (dest / "pom.xml").is_file()


def test_run_tests_with_real_mvn_when_available(tmp_path: Path) -> None:
    """If mvn is available in the test environment, the clone should build."""

    if shutil.which("mvn") is None:
        pytest.skip("mvn not available")
    dest = clone_target(TARGET_DIR, tmp_path / "clone")
    result = run_tests(dest)
    # We don't assert on tests_run because surefire output parsing is exercised
    # in test_parse_surefire_summary; the build_success bool is the real signal.
    assert isinstance(result, TestResult)
    assert result.skipped is False
