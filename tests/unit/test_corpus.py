"""Corpus loader + exemplar shape sanity."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from unidiff import PatchSet  # type: ignore[attr-defined]

from bug_triage.corpus import iter_resolution_files, load_resolutions

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLUTIONS_DIR = REPO_ROOT / "corpus" / "resolutions"
SEVERITIES = {"critical", "high", "medium", "low"}
COMPONENTS = {"api", "core", "util", "tests", "build"}


def test_corpus_size() -> None:
    """30 hand-written + 170 deterministic synthetic exemplars = 200."""
    files = iter_resolution_files(RESOLUTIONS_DIR)
    assert len(files) == 200


def test_each_resolution_has_required_keys() -> None:
    for path in iter_resolution_files(RESOLUTIONS_DIR):
        data = json.loads(path.read_text())
        for key in (
            "id",
            "bug_report",
            "root_cause",
            "fix_diff",
            "files_changed",
            "severity",
            "component",
            "resolved_at",
        ):
            assert key in data, f"{path.name} missing {key}"
        assert data["severity"] in SEVERITIES
        assert data["component"] in COMPONENTS
        assert isinstance(data["files_changed"], list) and data["files_changed"]


def test_each_diff_parses_with_unidiff() -> None:
    for path in iter_resolution_files(RESOLUTIONS_DIR):
        data = json.loads(path.read_text())
        patch = PatchSet(StringIO(data["fix_diff"]))
        assert len(patch) >= 1, f"{path.name} produced an empty patch"


def test_files_changed_match_diff_paths() -> None:
    for path in iter_resolution_files(RESOLUTIONS_DIR):
        data = json.loads(path.read_text())
        patch = PatchSet(StringIO(data["fix_diff"]))
        diff_paths = {f.path for f in patch}
        # files_changed should overlap the diff's referenced paths.
        assert (
            set(data["files_changed"]) & diff_paths
        ), f"{path.name} files_changed {data['files_changed']} disjoint from diff paths {diff_paths}"


def test_load_resolutions_builds_orm_rows() -> None:
    rows = load_resolutions(RESOLUTIONS_DIR)
    assert len(rows) == 200
    ids = {r.id for r in rows}
    assert "R001" in ids and "R030" in ids and "R200" in ids


def test_referenced_paths_exist_on_disk() -> None:
    for path in iter_resolution_files(RESOLUTIONS_DIR):
        data = json.loads(path.read_text())
        for rel in data["files_changed"]:
            target = REPO_ROOT / rel
            assert target.exists(), f"{path.name} references missing file {rel}"
