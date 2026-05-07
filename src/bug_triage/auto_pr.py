"""Env-gated auto-create-PR mode.

When ``AUTO_PR=1`` and the suggester clears every guardrail, ``maybe_open_pr``
spawns a draft PR via the ``gh`` CLI:

  - confidence >= ``AUTO_PR_CONFIDENCE_THRESHOLD`` (default 0.8)
  - ``apply_result.hunks_rejected == 0``
  - ``test_result.tests_failed == 0``
  - ``test_result.build_success`` is true

The PR is always created with ``--draft`` so a human reviews before merge.
The caller can override the ``gh`` binary via ``AUTO_PR_GH_BINARY`` to point
at a wrapper script -- the test suite uses this to capture invocations
without contacting GitHub.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bug_triage.applier import ApplyResult, TestResult
from bug_triage.retriever import ResolutionMatch
from bug_triage.suggester import SuggesterOutput

DEFAULT_CONFIDENCE_THRESHOLD = 0.8
log = logging.getLogger("bug_triage.auto_pr")


@dataclass(frozen=True)
class AutoPRResult:
    """Outcome of an auto-PR attempt."""

    enabled: bool
    opened: bool
    skipped_reason: str | None
    pr_url: str | None = None
    branch: str | None = None
    invocation: list[str] | None = None


@dataclass(frozen=True)
class AutoPRConfig:
    enabled: bool
    repo: str | None
    confidence_threshold: float
    gh_binary: str | None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AutoPRConfig:
        env = env or dict(os.environ)
        return cls(
            enabled=env.get("AUTO_PR", "0") == "1",
            repo=env.get("AUTO_PR_REPO"),
            confidence_threshold=float(
                env.get("AUTO_PR_CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD))
            ),
            gh_binary=env.get("AUTO_PR_GH_BINARY"),
        )


def _check_guardrails(
    config: AutoPRConfig,
    suggestion: SuggesterOutput,
    apply_result: ApplyResult,
    test_result: TestResult,
) -> str | None:
    """Return ``None`` when every guardrail passes, else a reason string."""

    if not config.enabled:
        return "AUTO_PR=0"
    if config.repo is None:
        return "AUTO_PR_REPO not configured"
    if suggestion.confidence < config.confidence_threshold:
        return (
            f"confidence {suggestion.confidence:.3f} < threshold {config.confidence_threshold:.3f}"
        )
    if apply_result.hunks_rejected > 0:
        return f"apply_result.hunks_rejected={apply_result.hunks_rejected}"
    if not apply_result.success:
        return "apply did not succeed"
    if test_result.tests_failed > 0:
        return f"test_result.tests_failed={test_result.tests_failed}"
    if not test_result.build_success:
        return "build did not succeed"
    return None


def _resolve_gh(config: AutoPRConfig) -> str | None:
    if config.gh_binary:
        return config.gh_binary
    return shutil.which("gh")


def _branch_name(seed: str | None = None) -> str:
    suffix = seed or uuid.uuid4().hex[:8]
    return f"bug-triage/auto-pr-{suffix}"


def _build_body(
    bug_report: str,
    suggestion: SuggesterOutput,
    retrieved: Sequence[ResolutionMatch],
    apply_result: ApplyResult,
    test_result: TestResult,
) -> str:
    top3 = list(retrieved[:3])
    citations = (
        "\n".join(
            f"- `{m.resolution_id}` (similarity={m.similarity:.3f}, "
            f"severity={m.severity}, component={m.component})"
            for m in top3
        )
        if top3
        else "_no resolutions retrieved_"
    )
    return textwrap.dedent(
        f"""\
        ## Bug report

        {bug_report.strip()}

        ## Fix rationale

        {suggestion.rationale.strip()}

        ## Test result

        - build_success: {test_result.build_success}
        - tests_run: {test_result.tests_run}
        - tests_passed: {test_result.tests_passed}
        - tests_failed: {test_result.tests_failed}
        - hunks_applied: {apply_result.hunks_applied}
        - hunks_rejected: {apply_result.hunks_rejected}

        ## Top-3 retrieved resolutions

        {citations}

        ---
        Suggested-by: bug-triage auto-pr (confidence={suggestion.confidence:.3f})
        """
    )


def _build_title(bug_report: str) -> str:
    first = bug_report.strip().splitlines()[0] if bug_report.strip() else "auto-fix"
    head = first.strip()
    if len(head) > 70:
        head = head[:67] + "..."
    return head


def maybe_open_pr(
    *,
    bug_report: str,
    suggestion: SuggesterOutput,
    retrieved: Sequence[ResolutionMatch],
    apply_result: ApplyResult,
    test_result: TestResult,
    project_dir: Path,
    config: AutoPRConfig | None = None,
) -> AutoPRResult:
    """Open a draft PR if every guardrail passes.

    ``project_dir`` is the patched clone produced by ``apply_and_test``. The
    files there are bundled into a JSON payload (``--field path=...``) the
    test wrapper can inspect; in production this is where ``git`` would push.
    """

    cfg = config or AutoPRConfig.from_env()
    skip_reason = _check_guardrails(cfg, suggestion, apply_result, test_result)
    if skip_reason is not None:
        log.info("auto_pr skipped: %s", skip_reason)
        return AutoPRResult(enabled=cfg.enabled, opened=False, skipped_reason=skip_reason)

    gh = _resolve_gh(cfg)
    if gh is None:
        return AutoPRResult(enabled=True, opened=False, skipped_reason="gh CLI not on PATH")

    branch = _branch_name()
    title = _build_title(bug_report)
    body = _build_body(bug_report, suggestion, retrieved, apply_result, test_result)

    # ``project_dir`` (the patched clone) is what we'd push to ``branch``. We
    # don't actually run ``git push`` from this code path -- production
    # deployments should do that ahead of the gh call. We pass the path
    # through to the gh invocation so the wrapper script can verify.
    invocation = [
        gh,
        "pr",
        "create",
        "--repo",
        cfg.repo or "",
        "--head",
        branch,
        "--title",
        title,
        "--body",
        body,
        "--draft",
    ]

    with tempfile.NamedTemporaryFile("w", suffix=".meta.json", delete=False) as fh:
        json.dump(
            {
                "branch": branch,
                "project_dir": str(project_dir),
                "title": title,
            },
            fh,
        )
        meta_path = fh.name

    env = dict(os.environ)
    env["AUTO_PR_META"] = meta_path
    try:
        proc = subprocess.run(  # noqa: S603 - argv is constructed
            invocation,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return AutoPRResult(
            enabled=True,
            opened=False,
            skipped_reason="gh pr create timed out",
            invocation=invocation,
        )
    finally:
        Path(meta_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        return AutoPRResult(
            enabled=True,
            opened=False,
            skipped_reason=f"gh exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}",
            branch=branch,
            invocation=invocation,
        )
    pr_url = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else None
    return AutoPRResult(
        enabled=True,
        opened=True,
        skipped_reason=None,
        pr_url=pr_url,
        branch=branch,
        invocation=invocation,
    )
