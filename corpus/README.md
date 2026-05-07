# corpus/

Two pieces:

1. **`target/`** — `calc-server`, the Java toy project (Maven, Java 21). The
   bug-triage retrieval corpus is grounded in this real, compiling codebase
   so resolution exemplars reference actual classes/methods, and so CI can
   detect drift between exemplars and the underlying Java code (`mvn -B verify`
   in the `java-build` job).

2. **`resolutions/`** — 30 hand-written `(bug_report, root_cause, fix_diff,
   files_changed, severity, component, resolved_at)` JSON files. The retriever
   embeds `bug_report + root_cause` and serves the top-3 most similar past
   resolutions for any incoming bug. Filenames are `R001.json` ... `R030.json`.

Production deployments would replace `resolutions/` by mining git history
(commit message + diff + JIRA ticket linked from the body). This prototype
ships hand-written exemplars so the pipeline is reproducible end-to-end.

## Layout

```
corpus/
├── target/                  # Maven project, real Java source
└── resolutions/
    ├── R001.json
    ├── ...
    └── R030.json
```

## Re-generate

```
python scripts/generate_corpus.py
```

This rewrites the 30 JSON files from the in-repo registry. Hand edits are
fine; the generator is idempotent and the source-of-truth registry lives in
`scripts/generate_corpus.py`.
