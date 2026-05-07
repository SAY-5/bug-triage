# calc-server

Tiny calculator HTTP service. This module exists so the bug-triage retrieval
corpus is grounded in a real, compiling Java codebase rather than abstract
synthetic strings. Resolution exemplars in `corpus/resolutions/` reference
files in this module by relative path (e.g. `corpus/target/src/main/java/com/example/calc/Calculator.java`).

This is not intended as a production service. CI runs `mvn -B verify` against
this module to catch drift between resolution exemplars and the underlying
Java code.

## Build

```
mvn -B verify
```

## Run

```
java -jar target/calc-server-0.1.0.jar 8080
```

Endpoints: `/add`, `/sub`, `/mul`, `/div`, `/eval`, `/healthz`.
