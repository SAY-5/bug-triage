# Architecture

## Closed-enum classification design

The classifier emits `{severity, component, confidence, reasoning}` with
severity drawn from `{critical, high, medium, low}` and component from
`{api, core, util, tests, build}`. The prompt declares these enums verbatim,
gives five hand-picked few-shot examples, and tells the model to output JSON
only. The output is parsed with `json.loads` and validated by a Pydantic
schema with `extra="forbid"`. Out-of-enum values, extra keys, missing keys,
or non-JSON output all raise `ClassifierError` rather than silently
returning a degraded label.

Why closed enums beat free-text labels: free-text drifts. After 100 reports
you have 100 component names ("backend", "back-end", "service", "api"). A
closed enum forces label collapse at the prompt boundary, and the Pydantic
validator catches drift the moment a provider produces something new.

## Retrieval-corpus design

The corpus is `(bug_report, root_cause, fix_diff, files_changed, severity,
component, resolved_at)` per resolution. Each `bug_report` references real
classes/methods that exist in the Java toy project under `corpus/target/`,
so:

- The retriever's similarity scores are anchored in real lexical content,
  not fabricated jargon.
- The suggester's `applies_to_files` references can be checked against
  files that actually exist (CI does this in the corpus tests).
- Drift between exemplars and code is mechanically detectable: the
  `java-build` job runs `mvn -B verify` and the corpus test suite checks
  every `files_changed` path against disk.

Why hand-written exemplars instead of mined history: scope. A production
deployment would mine git history (commit + diff + ticket link) to populate
this table. That mining step is a project of its own; this prototype keeps
the corpus shape stable so the indexer/retriever/suggester stay focused.

## Diff validation discipline

The suggester forces structured output `{suggested_diff, rationale,
confidence, applies_to_files, based_on_resolutions}`. The diff is run
through `unidiff.PatchSet`. If parsing fails — empty, malformed, the model
returned prose — the suggester zeros out the confidence and surfaces the
parse error. Downstream consumers can detect this with one boolean check
(`diff_parses`) instead of trying to repair model output.

The trade-off: a stricter parser would also verify the diff *applies* to
the current source. We deliberately stop at parse-validity. Apply-time
checks belong in a separate worker that has the working tree available; the
prompt step's job is to never emit syntactically invalid output.

## Prompt versioning approach

Prompt templates live as YAML under `src/bug_triage/prompts/` with a
`version` field. The `prompts.load()` cache reads them once. Every
`triage_results` row records `model_version` so prompt-rev/model-rev pairs
can be correlated when reading the audit log. Bumping a prompt only
requires editing the YAML and incrementing the version.

## Eval harness

The harness runs the full pipeline per case and scores six metrics:
`severity_match`, `component_match`, `top1_retrieval_match`,
`top3_retrieval_match`, `suggested_diff_parses`, and `mean_files_overlap`
(Jaccard between predicted and expected `files_changed`). It writes a JSON
baseline under `eval/baselines/`. CI's `eval-smoke` job runs the full suite
against FakeProvider and asserts retrieval and diff-parse thresholds; this
catches regressions in prompt assembly, embedder determinism, or the
retrieval pipeline.

## What's deliberately not here

- **No auto-application of diffs.** Suggester emits, downstream applies.
  Two services, two failure modes, two audit logs.
- **No agent loop.** One forward pass per request. No tool calls, no
  retries, no back-and-forth. If the diff doesn't parse, that's the answer.
- **No fine-tuning.** Prompts only. We bet on closed-enum validation +
  retrieval + structured output rather than a tuned classifier head.
- **No real-bug history scrape.** Corpus is hand-written; production would
  swap in a mining job. The corpus *shape* is the contract.
- **No multi-tenant auth.** The API has `/healthz`, `/v1/triage`,
  `/v1/resolutions`, `/v1/triage/{id}`. Putting it behind an auth proxy is
  the deployer's job.
