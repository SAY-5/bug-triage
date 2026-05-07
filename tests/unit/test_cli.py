"""CLI smoke tests via Click's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bug_triage.cli import cli


def test_index_prints_resolution_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HASH_EMBEDDER", "1")
    runner = CliRunner()
    result = runner.invoke(cli, ["index"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["resolutions"] == 30
    assert payload["dim"] == 384


def test_triage_command_runs_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HASH_EMBEDDER", "1")
    monkeypatch.setenv("PROVIDER", "fake")
    bug = tmp_path / "bug.txt"
    bug.write_text("Calculator.div returns Infinity for zero divisor at /div")
    runner = CliRunner()
    result = runner.invoke(cli, ["triage", "--file", str(bug)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "classification" in payload
    assert "retrieved" in payload
    assert "suggestion" in payload
    assert payload["diff_parses"] is True
    assert payload["retrieved"][0]["resolution_id"] == "R001"


def test_eval_run_writes_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HASH_EMBEDDER", "1")
    out = tmp_path / "baseline.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "eval",
            "run",
            "--suite",
            "triage_v1",
            "--provider",
            "fake",
            "--output",
            str(out),
            "--no-markdown",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["n"] == 20
    assert data["metrics"]["top1_retrieval_match"] >= 0.6
    assert len(data["cases"]) == 20
