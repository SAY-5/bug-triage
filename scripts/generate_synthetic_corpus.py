"""Generate 170 deterministic synthetic resolution exemplars (R031..R200).

The 30 hand-written exemplars in R001..R030 cover real bugs in the calc-server
codebase. To stress retrieval at scale we need a larger corpus. This script
emits 170 additional synthetic exemplars by combining:

  - bug-report templates (30 templates) describing a fault mode in plain English
  - Java method templates (a pool of fictional method names spread across the
    real files in corpus/target/)
  - severity / component pairs drawn round-robin from the closed enums

Determinism: a fixed seed and stable iteration order means rerunning this
script is a no-op (same files, same content). The generator is intentionally
hermetic -- no network, no Faker dependency. The "Faker" role is filled by a
small in-script vocabulary so CI doesn't need to install another package.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "corpus" / "resolutions"

CALC_FILE = "corpus/target/src/main/java/com/example/calc/Calculator.java"
PARSER_FILE = "corpus/target/src/main/java/com/example/calc/ExpressionParser.java"
SERVER_FILE = "corpus/target/src/main/java/com/example/calc/CalcServer.java"
VAL_FILE = "corpus/target/src/main/java/com/example/calc/Validation.java"
POM_FILE = "corpus/target/pom.xml"
TEST_FILE = "corpus/target/src/test/java/com/example/calc/CalculatorTest.java"

FILES_BY_COMPONENT: dict[str, list[str]] = {
    "core": [CALC_FILE, PARSER_FILE],
    "api": [SERVER_FILE],
    "util": [VAL_FILE],
    "tests": [TEST_FILE],
    "build": [POM_FILE],
}

# Pool of plausible-sounding fictional method names per file.
METHOD_TEMPLATES: dict[str, list[str]] = {
    CALC_FILE: [
        "addExact",
        "subExact",
        "mulExact",
        "divSafe",
        "modSafe",
        "powSafe",
        "incrementCounter",
        "resetCounter",
        "checkOverflow",
        "normalize",
    ],
    PARSER_FILE: [
        "tokenize",
        "parseRpn",
        "parseInfix",
        "popOperator",
        "balanceParens",
        "evaluateNode",
        "stripWhitespace",
        "parseNumber",
    ],
    SERVER_FILE: [
        "handleAdd",
        "handleSub",
        "handleMul",
        "handleDiv",
        "handleEval",
        "handleHealthz",
        "writeJsonError",
        "readBody",
    ],
    VAL_FILE: [
        "requireNonNull",
        "requireNonEmpty",
        "parseOperand",
        "rejectNaN",
        "validateLength",
        "validateRange",
    ],
    TEST_FILE: [
        "assertOverflow",
        "assertParses",
        "assertRejects",
        "stubServer",
        "fixtureBody",
    ],
    POM_FILE: [
        "junit-jupiter",
        "maven-compiler-plugin",
        "maven-surefire-plugin",
    ],
}

# Bug-report templates. Each is a (template, severity-bias, component-affinity).
# {method} is filled in from METHOD_TEMPLATES; {component} from the chosen file.
BUG_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "{cls}.{method} silently swallows {exception_type} and returns a default value, "
        "masking real failures from clients hitting /{endpoint}.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} throws NullPointerException when input is null instead of "
        "rejecting with IllegalArgumentException; surfaces as a 500 from /{endpoint}.",
        "high",
        "util",
    ),
    (
        "{cls}.{method} loses precision on large operand pairs causing wrong-answer "
        "responses on /{endpoint}.",
        "medium",
        "core",
    ),
    (
        "{cls}.{method} leaks a stack trace into the HTTP response body when the "
        "request is malformed; should map to a structured 400 instead.",
        "medium",
        "api",
    ),
    (
        "{cls}.{method} blocks the event loop for {n}ms under sustained load; the "
        "/{endpoint} endpoint times out under concurrent traffic.",
        "high",
        "api",
    ),
    (
        "{cls}.{method} produces non-deterministic ordering when two operations land "
        "in the same millisecond; tests that lock to wall-clock time become flaky.",
        "medium",
        "tests",
    ),
    (
        "{cls}.{method} reads from a pom property that no longer exists after the "
        "Maven 3.13 upgrade; the build fails on a fresh checkout.",
        "low",
        "build",
    ),
    (
        "{cls}.{method} returns Infinity instead of throwing ArithmeticException for "
        "the documented degenerate input.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} doesn't validate that input length is below the 4KB cap; a "
        "malicious /{endpoint} call can balloon memory.",
        "high",
        "util",
    ),
    (
        "{cls}.{method} skips an explicit null guard at the entry point, so callers "
        "see an opaque NPE rather than a clean validation error.",
        "medium",
        "util",
    ),
    (
        "{cls}.{method} swallows InterruptedException without restoring the thread's "
        "interrupt flag; downstream cancellation never propagates.",
        "medium",
        "core",
    ),
    (
        "{cls}.{method} closes the response writer before flushing, so the client "
        "sees a truncated JSON body from /{endpoint}.",
        "high",
        "api",
    ),
    (
        "{cls}.{method} uses == instead of .equals to compare boxed Long values; the "
        "comparison silently misclassifies inputs.",
        "medium",
        "core",
    ),
    (
        "{cls}.{method} accepts negative operands where the contract says positive "
        "only; missing range check on /{endpoint}.",
        "medium",
        "util",
    ),
    (
        "{cls}.{method} formats doubles via toString causing locale-dependent "
        "decimal separators in the response.",
        "low",
        "api",
    ),
    (
        "{cls}.{method} fails to handle an empty operand stack and crashes the "
        "parser before the per-request error mapper can run.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} computes the cache key on the unsanitized request body, "
        "letting attacker-controlled keys collide with legit ones.",
        "high",
        "api",
    ),
    (
        "{cls}.{method} relies on a system timezone for cutoff comparisons; tests "
        "pass locally and fail in CI because the runner is UTC.",
        "low",
        "tests",
    ),
    (
        "{cls}.{method} compiles only on JDK 17; the JDK 21 release flag in the "
        "pom is incompatible with one of its language features.",
        "low",
        "build",
    ),
    (
        "{cls}.{method} runs an O(n^2) hot loop where O(n) was claimed; /{endpoint} "
        "P95 latency degrades after the corpus crosses 5000 entries.",
        "medium",
        "core",
    ),
    (
        "{cls}.{method} does not propagate the trace id from the inbound request "
        "headers; logs from /{endpoint} can't be correlated with upstream calls.",
        "low",
        "api",
    ),
    (
        "{cls}.{method} writes log lines at INFO that include the raw request body, "
        "leaking PII once the audit log is shipped off-box.",
        "medium",
        "api",
    ),
    (
        "{cls}.{method} reads a system property at class-load time, so changing it "
        "via @SetSystemProperty in tests has no effect.",
        "medium",
        "tests",
    ),
    (
        "{cls}.{method} catches Throwable and continues, masking OOMError and "
        "preventing the JVM from failing fast.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} doesn't reset the AtomicLong counter between test cases so "
        "assertions see leaked state from a previous run.",
        "low",
        "tests",
    ),
    (
        "{cls}.{method} parses operands using Long.parseLong without a radix, so "
        "leading zeros are interpreted as decimal and the doc claims octal.",
        "low",
        "util",
    ),
    (
        "{cls}.{method} returns the wrong HTTP status (200) on partial failure "
        "instead of 207 or 500; clients can't distinguish success from degraded.",
        "medium",
        "api",
    ),
    (
        "{cls}.{method} doesn't enforce a max recursion depth, so a deeply nested "
        "expression on /{endpoint} can blow the stack.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} uses a non-thread-safe SimpleDateFormat; concurrent /{endpoint} "
        "calls produce occasional malformed timestamps.",
        "high",
        "core",
    ),
    (
        "{cls}.{method} mutates the input list in place; callers that share the list "
        "see surprising behaviour after a single /{endpoint} call.",
        "medium",
        "core",
    ),
]


COMPONENT_TO_CLASS = {
    CALC_FILE: "Calculator",
    PARSER_FILE: "ExpressionParser",
    SERVER_FILE: "CalcServer",
    VAL_FILE: "Validation",
    TEST_FILE: "CalculatorTest",
    POM_FILE: "pom",
}


def file_for_component(component: str) -> str:
    return FILES_BY_COMPONENT[component][0]


def build_diff(file_path: str, before: str, after: str) -> str:
    """Tiny synthetic unified diff. Same shape as the hand-written ones."""
    return (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f" // context\n"
        f"-{before}\n"
        f"+{after}\n"
    )


def generate(count: int = 170, start_id: int = 31, seed: int = 0xBEEF) -> list[dict[str, object]]:
    """Build ``count`` deterministic synthetic resolutions starting at ``start_id``."""

    rng = random.Random(seed)
    severities = ["critical", "high", "medium", "low"]
    components = list(FILES_BY_COMPONENT.keys())
    exception_types = [
        "IllegalArgumentException",
        "ArithmeticException",
        "NullPointerException",
        "IllegalStateException",
        "NumberFormatException",
    ]
    endpoints = ["add", "sub", "mul", "div", "eval", "healthz"]

    base_date = datetime(2026, 2, 1, 9, 0, 0, tzinfo=UTC)
    resolutions: list[dict[str, object]] = []
    for i in range(count):
        rid = f"R{start_id + i:03d}"
        template, sev_bias, comp_bias = BUG_TEMPLATES[i % len(BUG_TEMPLATES)]
        # Severity rotates but biases toward template's natural severity 1/3 of the time.
        severity = sev_bias if i % 3 == 0 else severities[i % len(severities)]
        # Component rotates but biases toward template's affinity 1/3 of the time.
        component = comp_bias if i % 3 == 0 else components[i % len(components)]
        file_path = file_for_component(component)
        cls = COMPONENT_TO_CLASS[file_path]
        method = rng.choice(METHOD_TEMPLATES[file_path])
        endpoint = rng.choice(endpoints)
        exc = rng.choice(exception_types)
        n_ms = rng.choice([50, 100, 200, 500])

        bug_report = template.format(
            cls=cls, method=method, endpoint=endpoint, exception_type=exc, n=n_ms
        )
        root_cause = (
            f"{cls}.{method} omits the documented guard for the failure path; "
            f"the analogous fix in earlier resolutions for {component} components "
            f"applies here."
        )
        before = f"// {method} missing guard"
        after = f"// {method} now guarded against {exc.lower()}"
        fix_diff = build_diff(file_path, before, after)

        resolved_at = base_date + timedelta(days=i // 4, hours=(i % 4) * 6)
        resolutions.append(
            {
                "id": rid,
                "bug_report": bug_report,
                "root_cause": root_cause,
                "fix_diff": fix_diff,
                "files_changed": [file_path],
                "severity": severity,
                "component": component,
                "resolved_at": resolved_at.isoformat(),
            }
        )
    return resolutions


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate()
    written = 0
    for row in rows:
        path = OUT_DIR / f"{row['id']}.json"
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        written += 1
    print(f"wrote {written} synthetic resolutions to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
