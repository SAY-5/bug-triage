"""``bug-triage`` Click CLI: index, triage --file, eval run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from bug_triage.corpus import embed_resolutions, load_resolutions
from bug_triage.embedder import build_embedder
from bug_triage.eval_harness import (
    build_default_runtime,
    report_to_markdown,
    run_eval,
    write_report,
)
from bug_triage.pipeline import run_triage
from bug_triage.providers import build_provider
from bug_triage.settings import get_settings


@click.group()
def cli() -> None:
    """Bug-triage CLI."""


@cli.command()
def index() -> None:
    """Embed every resolution exemplar and report the count.

    The hermetic path uses ``HashEmbedder``; production deployments swap in
    ``SentenceTransformersEmbedder``. Either way this is idempotent: it just
    materializes vectors, which the API/eval also produce on startup.
    """
    settings = get_settings()
    embedder = build_embedder(prefer_hash=settings.hash_embedder)
    rows = load_resolutions(settings.corpus_root / "resolutions")
    embed_resolutions(rows, embedder)
    click.echo(
        json.dumps(
            {"resolutions": len(rows), "embedder": type(embedder).__name__, "dim": embedder.dim}
        )
    )


@cli.command()
@click.option(
    "--file", "file_", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True
)
@click.option("--provider", default=None)
def triage(file_: Path, provider: str | None) -> None:
    """Run the full pipeline against a bug report read from a file."""
    settings = get_settings()
    embedder = build_embedder(prefer_hash=settings.hash_embedder)
    rows = load_resolutions(settings.corpus_root / "resolutions")
    embed_resolutions(rows, embedder)
    chat = build_provider(provider or settings.provider)
    bug_report = file_.read_text(encoding="utf-8").strip()
    outcome = run_triage(
        provider=chat,
        embedder=embedder,
        resolutions=rows,
        bug_report=bug_report,
        repo_root=settings.repo_root,
    )
    payload = {
        "classification": outcome.classification.output.model_dump(),
        "retrieved": [
            {
                "resolution_id": m.resolution_id,
                "similarity": round(m.similarity, 4),
                "severity": m.severity,
                "component": m.component,
            }
            for m in outcome.retrieved
        ],
        "suggestion": outcome.suggestion.output.model_dump(),
        "diff_parses": outcome.suggestion.diff_parses,
        "latency_ms": outcome.latency_ms,
    }
    click.echo(json.dumps(payload, indent=2))


@cli.group()
def eval() -> None:
    """Eval harness commands."""


@eval.command("run")
@click.option("--suite", default="triage_v1", show_default=True)
@click.option("--provider", default="fake", show_default=True)
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), required=True)
@click.option("--markdown/--no-markdown", default=True)
def eval_run(suite: str, provider: str, output: Path, markdown: bool) -> None:
    """Run an eval suite and write the JSON baseline."""
    settings = get_settings()
    chat, embedder = build_default_runtime(provider, prefer_hash=settings.hash_embedder)
    rows = load_resolutions(settings.corpus_root / "resolutions")
    embed_resolutions(rows, embedder)
    suite_path = settings.repo_root / "eval" / "suites" / f"{suite}.yaml"
    if not suite_path.exists():
        click.echo(f"suite not found: {suite_path}", err=True)
        sys.exit(2)
    report = run_eval(
        suite_path=suite_path,
        provider=chat,
        embedder=embedder,
        resolutions=rows,
        repo_root=settings.repo_root,
    )
    write_report(report, output)
    if markdown:
        click.echo(report_to_markdown(report))


if __name__ == "__main__":  # pragma: no cover
    cli()
