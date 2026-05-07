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
| `corpus/target/` | Maven `calc-server` toy project; the retrieval ground |
| `corpus/resolutions/` | 30 hand-written `(bug, fix)` JSON exemplars |
| `eval/suites/triage_v1.yaml` | 20 paraphrased incoming bug reports with ground truth |

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
