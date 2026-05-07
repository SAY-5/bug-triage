"""Tests for the env-gated auto-create-PR mode.

The tests exercise every guardrail and assert the captured ``gh pr create``
invocation contains the right argv when all guardrails pass. The ``gh``
binary is replaced via ``AUTO_PR_GH_BINARY`` with a wrapper script that
records its argv to a JSON file rather than calling GitHub.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Sequence
from pathlib import Path

import pytest

from bug_triage.applier import ApplyResult, TestResult
from bug_triage.auto_pr import (
    AutoPRConfig,
    AutoPRResult,
    _build_body,
    _build_title,
    maybe_open_pr,
)
from bug_triage.retriever import ResolutionMatch
from bug_triage.suggester import SuggesterOutput


def _make_match(rid: str, sim: float, sev: str = "high", comp: str = "core") -> ResolutionMatch:
    return ResolutionMatch(
        resolution_id=rid,
        similarity=sim,
        severity=sev,
        component=comp,
        bug_report=f"bug for {rid}",
        root_cause=f"cause for {rid}",
        fix_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=["x"],
    )


def _good_apply() -> ApplyResult:
    return ApplyResult(success=True, hunks_applied=1, hunks_rejected=0, conflict_files=[])


def _good_tests() -> TestResult:
    return TestResult(build_success=True, tests_run=4, tests_passed=4, tests_failed=0)


def _good_suggestion(confidence: float = 0.9) -> SuggesterOutput:
    return SuggesterOutput(
        suggested_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        rationale="Top retrieved resolution matches; applying analogous guard.",
        confidence=confidence,
        applies_to_files=["x"],
        based_on_resolutions=["R001", "R002", "R003"],
    )


def _retrieved() -> Sequence[ResolutionMatch]:
    return [
        _make_match("R001", 0.95),
        _make_match("R002", 0.81),
        _make_match("R003", 0.74),
    ]


def _make_gh_wrapper(tmp_path: Path) -> tuple[Path, Path]:
    """Create a fake ``gh`` script that records its argv to a JSON file."""

    capture = tmp_path / "captured.json"
    script = tmp_path / "fake-gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"path = {str(capture)!r}\n"
        "data = {'argv': sys.argv, 'env': {'AUTO_PR_META': os.environ.get('AUTO_PR_META')}}\n"
        "with open(path, 'w') as fh: json.dump(data, fh)\n"
        "print('https://github.com/user/repo/pull/123')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script, capture


def test_skipped_when_disabled() -> None:
    cfg = AutoPRConfig(enabled=False, repo="user/fork", confidence_threshold=0.8, gh_binary=None)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert isinstance(result, AutoPRResult)
    assert result.opened is False
    assert result.skipped_reason == "AUTO_PR=0"


def test_skipped_when_repo_missing() -> None:
    cfg = AutoPRConfig(enabled=True, repo=None, confidence_threshold=0.8, gh_binary=None)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.skipped_reason == "AUTO_PR_REPO not configured"


def test_skipped_when_confidence_below_threshold() -> None:
    cfg = AutoPRConfig(enabled=True, repo="user/fork", confidence_threshold=0.8, gh_binary=None)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(confidence=0.5),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.opened is False
    assert "confidence" in (result.skipped_reason or "")


def test_skipped_when_hunks_rejected() -> None:
    cfg = AutoPRConfig(enabled=True, repo="user/fork", confidence_threshold=0.8, gh_binary=None)
    bad_apply = ApplyResult(success=False, hunks_applied=0, hunks_rejected=2, conflict_files=["a"])
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=bad_apply,
        test_result=_good_tests(),
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.opened is False
    assert "hunks_rejected" in (result.skipped_reason or "")


def test_skipped_when_tests_failed() -> None:
    cfg = AutoPRConfig(enabled=True, repo="user/fork", confidence_threshold=0.8, gh_binary=None)
    bad_tests = TestResult(build_success=True, tests_run=4, tests_passed=3, tests_failed=1)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=bad_tests,
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.opened is False
    assert "tests_failed" in (result.skipped_reason or "")


def test_skipped_when_build_failed() -> None:
    cfg = AutoPRConfig(enabled=True, repo="user/fork", confidence_threshold=0.8, gh_binary=None)
    bad_tests = TestResult(build_success=False, tests_run=0, tests_passed=0, tests_failed=0)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=bad_tests,
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.opened is False
    assert "build" in (result.skipped_reason or "")


def test_invokes_gh_when_all_guardrails_pass(tmp_path: Path) -> None:
    """Happy path: capture the gh argv and assert it has the expected shape."""

    script, capture = _make_gh_wrapper(tmp_path)
    cfg = AutoPRConfig(
        enabled=True,
        repo="user/fork",
        confidence_threshold=0.8,
        gh_binary=str(script),
    )
    result = maybe_open_pr(
        bug_report="Calculator.div returns Infinity for zero divisor",
        suggestion=_good_suggestion(confidence=0.91),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=tmp_path / "patched",
        config=cfg,
    )
    assert result.opened is True
    assert result.skipped_reason is None
    assert result.pr_url == "https://github.com/user/repo/pull/123"
    assert result.branch is not None and result.branch.startswith("bug-triage/auto-pr-")
    payload = json.loads(capture.read_text(encoding="utf-8"))
    argv = payload["argv"]
    # First entry is the script path; the remaining argv must match what we expect.
    assert argv[1:6] == ["pr", "create", "--repo", "user/fork", "--head"]
    assert argv[6].startswith("bug-triage/auto-pr-")
    assert argv[7] == "--title"
    assert "Calculator.div" in argv[8]
    assert argv[9] == "--body"
    body = argv[10]
    assert "Top-3 retrieved resolutions" in body
    assert "R001" in body and "R002" in body and "R003" in body
    assert "Suggested-by: bug-triage auto-pr" in body
    assert argv[-1] == "--draft"


def test_skipped_when_gh_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PR", "1")
    monkeypatch.setenv("AUTO_PR_REPO", "user/fork")
    monkeypatch.delenv("AUTO_PR_GH_BINARY", raising=False)
    monkeypatch.setattr("bug_triage.auto_pr.shutil.which", lambda _t: None)
    cfg = AutoPRConfig.from_env()
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=Path("/tmp/x"),
        config=cfg,
    )
    assert result.opened is False
    assert result.skipped_reason == "gh CLI not on PATH"


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PR", "1")
    monkeypatch.setenv("AUTO_PR_REPO", "owner/repo")
    monkeypatch.setenv("AUTO_PR_CONFIDENCE_THRESHOLD", "0.95")
    monkeypatch.setenv("AUTO_PR_GH_BINARY", "/usr/bin/gh-stub")
    cfg = AutoPRConfig.from_env()
    assert cfg.enabled is True
    assert cfg.repo == "owner/repo"
    assert cfg.confidence_threshold == 0.95
    assert cfg.gh_binary == "/usr/bin/gh-stub"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AUTO_PR", "AUTO_PR_REPO", "AUTO_PR_CONFIDENCE_THRESHOLD", "AUTO_PR_GH_BINARY"):
        monkeypatch.delenv(var, raising=False)
    cfg = AutoPRConfig.from_env({})
    assert cfg.enabled is False
    assert cfg.repo is None
    assert cfg.confidence_threshold == 0.8
    assert cfg.gh_binary is None


def test_build_title_truncates_long_lines() -> None:
    long = "x" * 200
    assert len(_build_title(long)) <= 70


def test_build_body_renders_top3_citations() -> None:
    body = _build_body(
        "bug",
        _good_suggestion(),
        _retrieved(),
        _good_apply(),
        _good_tests(),
    )
    assert "R001" in body
    assert "R002" in body
    assert "R003" in body
    assert "tests_passed: 4" in body


def test_gh_failure_returns_skipped(tmp_path: Path) -> None:
    failing = tmp_path / "fail-gh"
    failing.write_text("#!/bin/sh\necho boom >&2\nexit 7\n", encoding="utf-8")
    failing.chmod(failing.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    cfg = AutoPRConfig(
        enabled=True, repo="user/fork", confidence_threshold=0.8, gh_binary=str(failing)
    )
    # Ensure the test-runner env doesn't leak a real AUTO_PR_GH_BINARY.
    os.environ.pop("AUTO_PR_GH_BINARY", None)
    result = maybe_open_pr(
        bug_report="x",
        suggestion=_good_suggestion(),
        retrieved=_retrieved(),
        apply_result=_good_apply(),
        test_result=_good_tests(),
        project_dir=tmp_path,
        config=cfg,
    )
    assert result.opened is False
    assert "gh exited 7" in (result.skipped_reason or "")
