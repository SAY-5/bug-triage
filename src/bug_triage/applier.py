"""Apply a suggested diff to a clone of corpus/target/ and run mvn -B verify.

Two responsibilities:

  - ``apply_diff`` writes the diff to a temp file, runs ``git apply`` against
    the clone, and reports counts of accepted vs rejected hunks.
  - ``run_tests`` runs ``mvn -B verify`` in the clone and parses surefire's
    summary for pass/fail counts.

Both functions degrade gracefully when the underlying tool isn't installed:
they return a ``skipped=True`` result with a reason rather than raising.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ApplyResult:
    success: bool
    hunks_applied: int
    hunks_rejected: int
    conflict_files: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class TestResult:
    """Outcome of ``mvn -B verify`` against a clone of corpus/target/.

    Named ``TestResult`` because it reports on Java unit-test execution; not a
    pytest fixture. The ``__test__`` flag tells pytest's collector to skip it.
    """

    __test__ = False

    build_success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    skipped: bool = False
    reason: str | None = None


def _which(tool: str) -> str | None:
    return shutil.which(tool)


def _count_hunks(diff: str) -> int:
    return sum(1 for line in diff.splitlines() if line.startswith("@@"))


def clone_target(source: Path, dest: Path) -> Path:
    """Copy ``corpus/target/`` (or any tree) to ``dest``. Returns ``dest``."""

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    return dest


def apply_diff(diff: str, project_dir: Path) -> ApplyResult:
    """Apply ``diff`` against ``project_dir`` using ``git apply``.

    The ``git apply --3way`` flow is used when the project_dir is itself a
    git working copy; we fall back to ``git apply --reject`` so that partial
    successes are visible. ``patch(1)`` is the secondary option when ``git``
    isn't on PATH.
    """

    diff_text = diff.strip()
    if not diff_text:
        return ApplyResult(success=False, hunks_applied=0, hunks_rejected=0, reason="empty diff")
    total_hunks = _count_hunks(diff_text)
    git = _which("git")
    if git is None:
        return ApplyResult(
            success=False,
            hunks_applied=0,
            hunks_rejected=total_hunks,
            skipped=True,
            reason="git not on PATH",
        )

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
        fh.write(diff_text)
        if not diff_text.endswith("\n"):
            fh.write("\n")
        patch_path = Path(fh.name)
    try:
        proc = subprocess.run(  # noqa: S603 - argv is constructed, not a shell string
            [git, "apply", "--reject", "--whitespace=nowarn", str(patch_path)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return ApplyResult(
            success=False,
            hunks_applied=0,
            hunks_rejected=total_hunks,
            reason="git apply timed out",
        )
    finally:
        patch_path.unlink(missing_ok=True)

    rejects = sorted(p.relative_to(project_dir).as_posix() for p in project_dir.rglob("*.rej"))
    rejected = len(rejects)
    applied = (
        max(0, total_hunks - rejected) if proc.returncode == 0 else max(0, total_hunks - rejected)
    )
    if proc.returncode != 0 and rejected == 0:
        # Whole-patch failure with no .rej artefacts -- count all hunks as rejected.
        rejected = total_hunks
        applied = 0
    success = proc.returncode == 0 and rejected == 0
    return ApplyResult(
        success=success,
        hunks_applied=applied,
        hunks_rejected=rejected,
        conflict_files=rejects,
        reason=None if success else (proc.stderr.strip() or proc.stdout.strip() or None),
    )


_TESTS_LINE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)"
)


def _parse_surefire(stdout: str) -> tuple[int, int, int]:
    """Pull the cumulative ``Tests run`` line that surefire emits at the end.

    Returns ``(tests_run, tests_passed, tests_failed)``. We sum failures and
    errors into ``tests_failed`` -- both are red, the distinction doesn't
    matter for the bench gate.
    """

    matches = list(_TESTS_LINE.finditer(stdout))
    if not matches:
        return 0, 0, 0
    # The final summary is what we want. Earlier lines are per-test-class.
    last = matches[-1]
    tests_run = int(last.group(1))
    failures = int(last.group(2))
    errors = int(last.group(3))
    skipped = int(last.group(4))
    failed = failures + errors
    passed = tests_run - failed - skipped
    return tests_run, max(0, passed), failed


def run_tests(project_dir: Path) -> TestResult:
    """Run ``mvn -B verify`` in ``project_dir`` and parse surefire output."""

    mvn = _which("mvn")
    if mvn is None:
        return TestResult(
            build_success=False,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            skipped=True,
            reason="mvn not on PATH",
        )
    try:
        proc = subprocess.run(  # noqa: S603 - argv is constructed
            [mvn, "-B", "verify"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            build_success=False,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            reason="mvn verify timed out",
        )
    tests_run, passed, failed = _parse_surefire(proc.stdout)
    return TestResult(
        build_success=proc.returncode == 0,
        tests_run=tests_run,
        tests_passed=passed,
        tests_failed=failed,
        reason=None if proc.returncode == 0 else "mvn verify exited non-zero",
    )


def apply_and_test(diff: str, *, source: Path, work_dir: Path) -> tuple[ApplyResult, TestResult]:
    """Convenience: clone ``source`` -> ``work_dir``, apply, run tests."""

    project = clone_target(source, work_dir)
    apply_result = apply_diff(diff, project)
    if not apply_result.success:
        return apply_result, TestResult(
            build_success=False,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            skipped=apply_result.skipped,
            reason=apply_result.reason or "diff did not apply cleanly",
        )
    test_result = run_tests(project)
    return apply_result, test_result


def cleanup(*paths: Path) -> None:
    """Remove the listed paths, ignoring missing entries."""

    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
