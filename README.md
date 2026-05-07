# bug-triage

Python service that classifies incoming bug reports by severity and component,
retrieves similar past resolutions from a corpus of (bug-report, fix) pairs
grounded in a real Java toy project, and suggests a unified-diff fix with a
short rationale. Exposes a REST API and a CLI.

## Hermetic baseline (FakeProvider, HashEmbedder)

| metric | score |
| --- | --- |
| severity_match | 0.60 |
| component_match | 0.70 |
| top1_retrieval_match | 1.00 |
| top3_retrieval_match | 1.00 |
| suggested_diff_parses | 1.00 |
| mean_files_overlap | 0.625 |

FakeProvider hermetic baseline against the 20-case `triage_v1` suite (n=20,
HashEmbedder, scripted FakeProvider). Reproduce with `make eval`. The full
per-case breakdown is committed at `eval/baselines/triage_fake.json`.

## 200-resolution bench (HashEmbedder + FakeProvider, 50 inputs)

| metric | value |
| --- | --- |
| corpus_size | 200 |
| num_inputs | 50 |
| top_1_rate | 0.70 |
| top_3_rate | 0.94 |
| latency_p50_ms | ~10 |
| latency_p95_ms | ~12 |

These numbers come from `make bench` against the merged 30+170 corpus (the
30 hand-written exemplars cover real Calculator/ExpressionParser/Validation
faults; the 170 synthetic exemplars are emitted by
`scripts/generate_synthetic_corpus.py` as bug-template x Java-method-template
combinations under a fixed seed). Half the bench inputs reuse a corpus
report verbatim; the other half perturb it with a leading prefix and a
trimmed first word, so the top-1/top-3 rates measure paraphrase resilience
of the hash embedder rather than identity lookups. Re-run with
`make bench-regress`; CI fails if top_1 or top_3 drop by >0.05 absolute or
P95 latency more than doubles.

### Synthetic-corpus generator process

`scripts/generate_synthetic_corpus.py` generates R031..R200 by combining:

1. 30 bug-report templates that name a fault mode (silently-swallowed
   exception, NPE, precision loss, leaked stack trace, etc.).
2. A pool of fictional method names per file in `corpus/target/` so each
   bug refers to a real class with a plausible (fictional) method.
3. Severity and component picks that rotate through the closed enums but
   bias toward each template's natural affinity 1/3 of the time.

The script is deterministic (fixed seed 0xBEEF, stable iteration order),
hermetic (no network, no Faker dependency -- vocabulary is in-script), and
idempotent (rerunning produces byte-identical files).

Reading the table:
- The 1.00 retrieval scores reflect the deterministic hash embedder against
  hand-written exemplars whose vocabulary intentionally overlaps the eval
  cases. Real-LLM embeddings would score lower on adversarial paraphrase.
- The 0.60 / 0.70 classifier scores come from FakeProvider's keyword
  heuristics and are the realistic floor for this prototype, not a ceiling
  for a real LLM. They prove the validation seam (Pydantic + closed enums)
  fires correctly under both hits and misses.
- `mean_files_overlap=0.625` is Jaccard between the suggester's
  `applies_to_files` and ground-truth `files_changed`. FakeProvider takes
  the top-2 files from the retrieved exemplars; ground truth is usually a
  single file, so Jaccard caps at 0.5 unless the top retrieval is exact.

## What this studies

- **Closed-enum classification with structured-output validation.** The
  classifier prompt pins severity to `{critical, high, medium, low}` and
  component to `{api, core, util, tests, build}`. Pydantic enforces the
  enums; out-of-enum values raise `ClassifierError` so misbehaving providers
  are loud, not silent.
- **Retrieval-augmented fix suggestion.** The suggester prompt receives the
  top-3 most similar past resolutions plus the current contents of the
  relevant Java source files. The LLM produces a unified diff; `unidiff`
  parses it as a gate.
- **Why a real Java codebase as the retrieval ground.** Resolution exemplars
  reference real classes/methods (`Calculator.div`, `ExpressionParser.evaluate`,
  `Validation.parseOperand`, `CalcServer.parseQuery`). CI runs `mvn -B verify`
  against `corpus/target/` to detect drift.
- **Prompt versioning.** Templates live in `src/bug_triage/prompts/*.yaml`
  with a `version` pin recorded in every persisted `triage_results` row.

## Modules

| module | purpose |
| --- | --- |
| `bug_triage.classifier` | severity+component closed-enum classifier |
| `bug_triage.retriever` | pgvector cosine retrieval + in-memory variant |
| `bug_triage.suggester` | retrieval-augmented diff suggester with `unidiff` parse gate |
| `bug_triage.embedder` | `HashEmbedder` (hermetic) + `SentenceTransformersEmbedder` |
| `bug_triage.providers` | `ChatProvider` Protocol + Fake / Anthropic / OpenAI |
| `bug_triage.pipeline` | classify -> retrieve -> suggest end-to-end |
| `bug_triage.api` | FastAPI surface (`/v1/triage`, `/v1/resolutions`, `/healthz`) |
| `bug_triage.cli` | Click CLI: `bug-triage index`, `triage --file`, `eval run` |
| `bug_triage.eval_harness` | per-case scoring + JSON/Markdown report |
| `bug_triage.applier` | apply suggested diff to a clone of `corpus/target/` and run `mvn -B verify` |
| `corpus/target/` | Maven `calc-server` toy project; the retrieval ground |
| `corpus/resolutions/` | 30 hand-written + 170 synthetic `(bug, fix)` JSON exemplars (200 total) |
| `bench/` | bench harness + bench-regress gate over the 200-resolution corpus |
| `eval/suites/triage_v1.yaml` | 20 paraphrased incoming bug reports with ground truth |

## Diff apply-and-test loop

`POST /v1/triage` accepts an optional `apply_and_test: true` flag. When set,
after the suggester returns a diff the API:

1. Copies `corpus/target/` into a temp directory.
2. Runs `git apply --reject` against the clone with the suggested diff.
3. If apply succeeds with zero rejected hunks, runs `mvn -B verify` and
   parses the surefire summary line for `tests_run`, `tests_passed`,
   `tests_failed`.
4. Returns `apply_result` and `test_result` alongside the usual response.

Both stages degrade gracefully:

- If `git` isn't on PATH, `apply_result.skipped=true` with `reason="git not on PATH"`.
- If `mvn` isn't on PATH, `test_result.skipped=true` with `reason="mvn not on PATH"`.

The `apply-and-test-smoke` CI job sets up JDK 21 + Maven and runs
`scripts/apply_and_test_smoke.py` against three hand-picked resolutions
(R001, R005, R006) so each PR exercises the full loop.

## Quickstart

```bash
poetry install --with dev
make java-build               # mvn -B verify in corpus/target/
HASH_EMBEDDER=1 make eval     # writes eval/baselines/triage_fake.json
```

Run the API against pgvector:

```bash
docker compose up -d postgres
make migrate
make seed
poetry run uvicorn bug_triage.api:app --reload
```

```bash
curl -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"bug_report":"Calculator.div returns Infinity instead of throwing on zero divisor"}'
```

## Architecture

```
                    +-----------------------------+
   bug report  -->  | classifier (closed enums,   |
                    | structured-output gated)    |
                    +--------------+--------------+
                                   |
                                   v
+------------------+      +-----------------------+
| HashEmbedder /   | -->  | retriever             |
| SentenceTrans.   |      | (pgvector cosine, k=3)|
+------------------+      +-----------+-----------+
                                      |
                                      v
                          +-----------------------+
                          | suggester             |
                          | (LLM + retrieved      |
                          | exemplars + Java src; |
                          | unidiff parse gate)   |
                          +-----------+-----------+
                                      |
                                      v
                          +-----------------------+
                          | persistence           |
                          | (triage_results row)  |
                          +-----------------------+
```

## What this is *not*

- Not an auto-merge bot. The suggester emits a diff and a rationale; nothing
  applies them or opens a PR.
- Not connected to CI. There's no GitHub webhook, no JIRA integration, no
  Slack handler.
- Not fine-tuned. Prompts only. The closed-enum gate keeps the classifier
  honest; everything else is retrieval + structured output.
- Not mining real bug history. The corpus is hand-written. A production
  deployment would replace `corpus/resolutions/` with a job that mines git
  history (commit message + diff + linked ticket).
- Not benchmarked against real LLMs. The numbers in the table above are from
  FakeProvider; bring your own keys to evaluate Anthropic/OpenAI.

## License

MIT — see `LICENSE`.
