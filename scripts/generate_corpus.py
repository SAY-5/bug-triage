"""Generate the 30 hand-designed resolution exemplars on disk.

Each exemplar:
  - bug_report: 1-3 sentences naming a real class/method in the calc-server codebase
  - root_cause: 1 sentence
  - fix_diff: a unified diff against a real file under corpus/target/
  - files_changed: list of repo-relative paths that match the diff
  - severity: critical | high | medium | low
  - component: api | core | util | tests | build
  - resolved_at: ISO-8601 with explicit dates
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "corpus" / "resolutions"


CALC_FILE = "corpus/target/src/main/java/com/example/calc/Calculator.java"
PARSER_FILE = "corpus/target/src/main/java/com/example/calc/ExpressionParser.java"
SERVER_FILE = "corpus/target/src/main/java/com/example/calc/CalcServer.java"
VAL_FILE = "corpus/target/src/main/java/com/example/calc/Validation.java"
POM_FILE = "corpus/target/pom.xml"
TEST_FILE = "corpus/target/src/test/java/com/example/calc/CalculatorTest.java"


def diff(file_path: str, before: str, after: str) -> str:
    """Build a tiny synthetic unified diff. Real enough that ``unidiff`` parses it.

    Hunk header is `@@ -1,2 +1,2 @@` and the body has one context line plus
    one removal and one addition; old=2 lines (context+removal), new=2 lines
    (context+addition).
    """
    return (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f" // context\n"
        f"-{before}\n"
        f"+{after}\n"
    )


RESOLUTIONS = [
    {
        "id": "R001",
        "bug_report": "Calculator.div returns Infinity when b is zero instead of throwing ArithmeticException; clients see a malformed numeric response from the /div endpoint.",
        "root_cause": "Division-by-zero guard was missing in Calculator.div; the method delegated straight to Java's IEEE-754 division which produces Infinity rather than raising.",
        "fix_diff": diff(
            CALC_FILE,
            "// no zero check",
            'if (b == 0L) throw new ArithmeticException("division by zero");',
        ),
        "files_changed": [CALC_FILE],
        "severity": "high",
        "component": "core",
        "resolved_at": "2026-01-04T10:15:00+00:00",
    },
    {
        "id": "R002",
        "bug_report": "Calculator.add silently overflows on Long.MAX_VALUE inputs, returning wrong results; the /add endpoint should reject overflow rather than wrap.",
        "root_cause": "Calculator.add used `+` instead of Math.addExact, so overflow wrapped to negative numbers without raising.",
        "fix_diff": diff(CALC_FILE, "return a + b;", "return Math.addExact(a, b);"),
        "files_changed": [CALC_FILE],
        "severity": "high",
        "component": "core",
        "resolved_at": "2026-01-09T13:00:00+00:00",
    },
    {
        "id": "R003",
        "bug_report": "Calculator.mul wraps silently for large operand pairs at the /mul endpoint, returning numbers smaller than either input.",
        "root_cause": "Multiplication used `*` instead of Math.multiplyExact, allowing silent overflow.",
        "fix_diff": diff(CALC_FILE, "return a * b;", "return Math.multiplyExact(a, b);"),
        "files_changed": [CALC_FILE],
        "severity": "high",
        "component": "core",
        "resolved_at": "2026-01-12T08:30:00+00:00",
    },
    {
        "id": "R004",
        "bug_report": "Calculator.sub overflows silently when subtracting Long.MIN_VALUE from a positive operand at /sub.",
        "root_cause": "Subtraction used `-` instead of Math.subtractExact, so overflow wrapped silently.",
        "fix_diff": diff(CALC_FILE, "return a - b;", "return Math.subtractExact(a, b);"),
        "files_changed": [CALC_FILE],
        "severity": "high",
        "component": "core",
        "resolved_at": "2026-01-15T11:30:00+00:00",
    },
    {
        "id": "R005",
        "bug_report": "Calculator.invocations counter races under concurrent /add load, undercounting requests by ~3%.",
        "root_cause": "The invocations field was a plain `long` updated with `++`, which is not atomic across threads.",
        "fix_diff": diff(
            CALC_FILE,
            "private static long INVOCATIONS = 0;",
            "private static final java.util.concurrent.atomic.AtomicLong INVOCATIONS = new java.util.concurrent.atomic.AtomicLong();",
        ),
        "files_changed": [CALC_FILE],
        "severity": "medium",
        "component": "core",
        "resolved_at": "2026-01-18T14:45:00+00:00",
    },
    {
        "id": "R006",
        "bug_report": "ExpressionParser.evaluate throws NullPointerException when given a null expression instead of a clean IllegalArgumentException.",
        "root_cause": "The parser assumed a non-null input; null was never validated at the entry point.",
        "fix_diff": diff(
            PARSER_FILE, "// no null check", 'Objects.requireNonNull(expression, "expression");'
        ),
        "files_changed": [PARSER_FILE],
        "severity": "medium",
        "component": "core",
        "resolved_at": "2026-01-20T09:10:00+00:00",
    },
    {
        "id": "R007",
        "bug_report": "ExpressionParser silently accepts unbalanced parentheses like '2 * (3 + 4' and evaluates to a wrong number instead of erroring.",
        "root_cause": "RPN conversion did not check for a trailing '(' on the operator stack at the end of input.",
        "fix_diff": diff(
            PARSER_FILE,
            "// no balance check",
            'if ("(".equals(top)) throw new IllegalArgumentException("unbalanced parentheses");',
        ),
        "files_changed": [PARSER_FILE],
        "severity": "high",
        "component": "core",
        "resolved_at": "2026-01-22T16:25:00+00:00",
    },
    {
        "id": "R008",
        "bug_report": "ExpressionParser tokenizer rejects negative-number literals like '-3 + 4', failing with 'unexpected character'.",
        "root_cause": "The tokenizer treated every '-' as an operator, so a leading minus could not start a number literal.",
        "fix_diff": diff(
            PARSER_FILE,
            "// always operator",
            "if (c == '-' && num.isEmpty() && (out.isEmpty() || isOperator(out.get(out.size()-1)))) num.append(c);",
        ),
        "files_changed": [PARSER_FILE],
        "severity": "medium",
        "component": "core",
        "resolved_at": "2026-01-26T10:50:00+00:00",
    },
    {
        "id": "R009",
        "bug_report": "ExpressionParser stack underflows on malformed input like '+ 1 2', returning a confusing NoSuchElementException.",
        "root_cause": "evalRpn popped the operand stack without checking it had two values, propagating an unrelated exception type.",
        "fix_diff": diff(
            PARSER_FILE,
            "// no size check",
            'if (stack.size() < 2) throw new IllegalArgumentException("malformed expression");',
        ),
        "files_changed": [PARSER_FILE],
        "severity": "medium",
        "component": "core",
        "resolved_at": "2026-01-28T12:35:00+00:00",
    },
    {
        "id": "R010",
        "bug_report": "ExpressionParser leaves residual values on the stack for inputs like '1 2 +', returning the last operand silently.",
        "root_cause": "evalRpn only checked stack.isEmpty() at the end; it should require exactly one value.",
        "fix_diff": diff(
            PARSER_FILE,
            "// no final check",
            'if (stack.size() != 1) throw new IllegalArgumentException("malformed expression");',
        ),
        "files_changed": [PARSER_FILE],
        "severity": "medium",
        "component": "core",
        "resolved_at": "2026-02-01T08:05:00+00:00",
    },
    {
        "id": "R011",
        "bug_report": "Validation.parseOperand accepts blank or whitespace-only strings, allowing /add?a= to crash deeper in Calculator with a misleading NumberFormatException.",
        "root_cause": "isBlank check was missing; the early validation step let empty input through.",
        "fix_diff": diff(
            VAL_FILE,
            "// no blank check",
            'if (raw == null || raw.isBlank()) throw new IllegalArgumentException("missing operand: " + name);',
        ),
        "files_changed": [VAL_FILE],
        "severity": "medium",
        "component": "util",
        "resolved_at": "2026-02-03T11:20:00+00:00",
    },
    {
        "id": "R012",
        "bug_report": "Validation.parseOperand rejects values larger than 1e9 even in callers that want unbounded operands; the cap should be configurable but at least documented.",
        "root_cause": "MAX_OPERAND was a hard-coded magic number with no bounds-check error message naming the limit.",
        "fix_diff": diff(
            VAL_FILE,
            "// missing bounds error",
            'throw new IllegalArgumentException("operand " + name + " out of range [" + -MAX_OPERAND + ", " + MAX_OPERAND + "]");',
        ),
        "files_changed": [VAL_FILE],
        "severity": "low",
        "component": "util",
        "resolved_at": "2026-02-05T14:00:00+00:00",
    },
    {
        "id": "R013",
        "bug_report": "Validation.requireNonEmpty allows whitespace-only strings through to /eval, which then fails inside the parser with a confusing 'empty expression' message far from the origin.",
        "root_cause": "requireNonEmpty only checked null but not isBlank.",
        "fix_diff": diff(
            VAL_FILE,
            "if (raw == null) throw ...",
            'if (raw == null || raw.isBlank()) throw new IllegalArgumentException("missing field: " + name);',
        ),
        "files_changed": [VAL_FILE],
        "severity": "medium",
        "component": "util",
        "resolved_at": "2026-02-07T09:25:00+00:00",
    },
    {
        "id": "R014",
        "bug_report": "Validation.parseOperand passes the original NumberFormatException message through unchanged, leaking 'For input string: ...' to clients.",
        "root_cause": "parseOperand caught NumberFormatException but did not wrap it in a domain-specific message.",
        "fix_diff": diff(
            VAL_FILE,
            "throw nfe;",
            'throw new IllegalArgumentException("operand " + name + " is not an integer: " + raw, nfe);',
        ),
        "files_changed": [VAL_FILE],
        "severity": "low",
        "component": "util",
        "resolved_at": "2026-02-09T15:50:00+00:00",
    },
    {
        "id": "R015",
        "bug_report": "CalcServer /add endpoint returns 500 with a stack trace when query parameters are missing instead of a 400 with a clean message.",
        "root_cause": "binaryOp did not catch IllegalArgumentException from Validation; it propagated to the default error handler.",
        "fix_diff": diff(
            SERVER_FILE,
            "// no catch",
            "} catch (IllegalArgumentException iae) { respond(ex, 400, iae.getMessage()); }",
        ),
        "files_changed": [SERVER_FILE],
        "severity": "high",
        "component": "api",
        "resolved_at": "2026-02-11T13:30:00+00:00",
    },
    {
        "id": "R016",
        "bug_report": "CalcServer /div endpoint returns 500 on division by zero instead of a 422 Unprocessable Entity with the arithmetic error.",
        "root_cause": "ArithmeticException from Calculator.div was not caught and mapped to a 422 response.",
        "fix_diff": diff(
            SERVER_FILE,
            "// no arith catch",
            "} catch (ArithmeticException ae) { respond(ex, 422, ae.getMessage()); }",
        ),
        "files_changed": [SERVER_FILE],
        "severity": "high",
        "component": "api",
        "resolved_at": "2026-02-13T16:10:00+00:00",
    },
    {
        "id": "R017",
        "bug_report": "CalcServer /eval endpoint truncates UTF-8 multi-byte responses because Content-Length was set to the string length instead of the byte length.",
        "root_cause": "respond() called sendResponseHeaders with body.length() instead of bytes.length, miscounting non-ASCII responses.",
        "fix_diff": diff(
            SERVER_FILE,
            "ex.sendResponseHeaders(status, body.length());",
            "ex.sendResponseHeaders(status, bytes.length);",
        ),
        "files_changed": [SERVER_FILE],
        "severity": "medium",
        "component": "api",
        "resolved_at": "2026-02-15T11:05:00+00:00",
    },
    {
        "id": "R018",
        "bug_report": "CalcServer.parseQuery throws StringIndexOutOfBoundsException when a query parameter has no '=' sign, instead of treating it as a flag.",
        "root_cause": "indexOf('=') returning -1 was not handled before the substring call.",
        "fix_diff": diff(
            SERVER_FILE,
            "out.put(part.substring(0, eq), part.substring(eq + 1));",
            'if (eq < 0) out.put(part, ""); else out.put(part.substring(0, eq), part.substring(eq + 1));',
        ),
        "files_changed": [SERVER_FILE],
        "severity": "medium",
        "component": "api",
        "resolved_at": "2026-02-17T09:40:00+00:00",
    },
    {
        "id": "R019",
        "bug_report": "CalcServer /healthz endpoint is missing; load balancer reports the calc-server as unhealthy after deployment.",
        "root_cause": "No HTTP handler was registered for /healthz; the deploy template assumed one existed.",
        "fix_diff": diff(
            SERVER_FILE,
            "// no healthz",
            'server.createContext("/healthz", ex -> respond(ex, 200, "ok"));',
        ),
        "files_changed": [SERVER_FILE],
        "severity": "high",
        "component": "api",
        "resolved_at": "2026-02-19T14:15:00+00:00",
    },
    {
        "id": "R020",
        "bug_report": "CalcServer hard-codes port 8080 with no override, so deployments behind a reverse proxy on a different port fail to start.",
        "root_cause": "main() ignored argv and constructed InetSocketAddress(8080) unconditionally.",
        "fix_diff": diff(
            SERVER_FILE,
            "new InetSocketAddress(8080)",
            "new InetSocketAddress(args.length > 0 ? Integer.parseInt(args[0]) : 8080)",
        ),
        "files_changed": [SERVER_FILE],
        "severity": "medium",
        "component": "api",
        "resolved_at": "2026-02-21T08:55:00+00:00",
    },
    {
        "id": "R021",
        "bug_report": "Maven build fails with 'invalid target release: 21' on CI runners that only have JDK 17, because pom.xml requires release 21 without a fallback.",
        "root_cause": "maven.compiler.release was set to 21 but the CI matrix did not pin Temurin 21.",
        "fix_diff": diff(
            POM_FILE,
            "<maven.compiler.release>17</maven.compiler.release>",
            "<maven.compiler.release>21</maven.compiler.release>",
        ),
        "files_changed": [POM_FILE],
        "severity": "medium",
        "component": "build",
        "resolved_at": "2026-02-23T10:25:00+00:00",
    },
    {
        "id": "R022",
        "bug_report": "Maven build pulls junit-jupiter at runtime scope, bloating the jar and causing transitive conflicts with downstream projects.",
        "root_cause": "junit-jupiter dependency was missing the test scope.",
        "fix_diff": diff(POM_FILE, "<scope>compile</scope>", "<scope>test</scope>"),
        "files_changed": [POM_FILE],
        "severity": "medium",
        "component": "build",
        "resolved_at": "2026-02-25T13:50:00+00:00",
    },
    {
        "id": "R023",
        "bug_report": "Manifest in calc-server.jar is missing Main-Class, so 'java -jar calc-server-0.1.0.jar' fails with 'no main manifest attribute'.",
        "root_cause": "maven-jar-plugin was not configured with a manifest mainClass entry.",
        "fix_diff": diff(
            POM_FILE,
            "<!-- no manifest -->",
            "<archive><manifest><mainClass>com.example.calc.CalcServer</mainClass></manifest></archive>",
        ),
        "files_changed": [POM_FILE],
        "severity": "high",
        "component": "build",
        "resolved_at": "2026-02-27T16:35:00+00:00",
    },
    {
        "id": "R024",
        "bug_report": "Maven Surefire runs zero tests in CI; the test compile target reports 'no tests in this project' even though CalculatorTest exists.",
        "root_cause": "Surefire 2.x was inherited from the parent and could not discover JUnit 5 platform tests; 3.x is required.",
        "fix_diff": diff(POM_FILE, "<version>2.22.2</version>", "<version>3.2.5</version>"),
        "files_changed": [POM_FILE],
        "severity": "medium",
        "component": "build",
        "resolved_at": "2026-03-01T09:20:00+00:00",
    },
    {
        "id": "R025",
        "bug_report": "CalculatorTest is flaky on parallel runs because Calculator.invocations leaks state between tests; assertEquals fails intermittently.",
        "root_cause": "Tests did not reset the static counter; parallel execution inherited a non-zero starting value.",
        "fix_diff": diff(
            TEST_FILE,
            "// no reset",
            "@BeforeEach void resetCounter() { Calculator.resetForTests(); }",
        ),
        "files_changed": [TEST_FILE],
        "severity": "medium",
        "component": "tests",
        "resolved_at": "2026-03-03T11:55:00+00:00",
    },
    {
        "id": "R026",
        "bug_report": "CalculatorTest does not assert that Calculator.div throws ArithmeticException on zero divisor; the test silently passes even when the guard is missing.",
        "root_cause": "Test coverage gap: no assertion of the throw contract for division by zero.",
        "fix_diff": diff(
            TEST_FILE,
            "// no zero test",
            "assertThrows(ArithmeticException.class, () -> Calculator.div(1L, 0L));",
        ),
        "files_changed": [TEST_FILE],
        "severity": "low",
        "component": "tests",
        "resolved_at": "2026-03-05T15:10:00+00:00",
    },
    {
        "id": "R027",
        "bug_report": "ExpressionParser CalculatorTest case for parenthesized expressions like '2 * (3 + 4)' is missing, so regressions in operator precedence go undetected.",
        "root_cause": "No JUnit case exercised mixed precedence with parentheses against ExpressionParser.evaluate.",
        "fix_diff": diff(
            TEST_FILE,
            "// no precedence test",
            'assertEquals(14.0, ExpressionParser.evaluate("2 * (3 + 4)"));',
        ),
        "files_changed": [TEST_FILE],
        "severity": "low",
        "component": "tests",
        "resolved_at": "2026-03-07T08:45:00+00:00",
    },
    {
        "id": "R028",
        "bug_report": "Validation.parseOperand has no test for whitespace-only operands; a regression in the isBlank check would go unnoticed.",
        "root_cause": "Missing assertThrows case for blank operand input in CalculatorTest.",
        "fix_diff": diff(
            TEST_FILE,
            "// no blank test",
            'assertThrows(IllegalArgumentException.class, () -> Validation.parseOperand("a", "  "));',
        ),
        "files_changed": [TEST_FILE],
        "severity": "low",
        "component": "tests",
        "resolved_at": "2026-03-09T13:00:00+00:00",
    },
    {
        "id": "R029",
        "bug_report": "CalcServer.parseQuery production crash log shows IndexOutOfBoundsException in deployment when query parameters arrive URL-encoded with '+' for space; tests never exercised this.",
        "root_cause": "parseQuery treats '+' as a literal character and indices into substring without decoding URL encoding; tests did not cover '+'.",
        "fix_diff": diff(
            TEST_FILE,
            "// no urlencoded test",
            'assertEquals("hi there", java.net.URLDecoder.decode("hi+there", java.nio.charset.StandardCharsets.UTF_8));',
        ),
        "files_changed": [TEST_FILE],
        "severity": "high",
        "component": "tests",
        "resolved_at": "2026-03-11T16:25:00+00:00",
    },
    {
        "id": "R030",
        "bug_report": "Calculator.resetForTests is package-private but the CalculatorTest in the same package fails to call it because the test source root is wrongly mapped to a different package; CI run reports 'cannot find symbol'.",
        "root_cause": "src/test/java was created under com/example/Calc instead of com/example/calc; case mismatch hid the package on case-insensitive filesystems.",
        "fix_diff": diff(TEST_FILE, "package com.example.Calc;", "package com.example.calc;"),
        "files_changed": [TEST_FILE],
        "severity": "medium",
        "component": "tests",
        "resolved_at": "2026-03-13T10:40:00+00:00",
    },
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for entry in RESOLUTIONS:
        path = OUT_DIR / f"{entry['id']}.json"
        path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(RESOLUTIONS)} resolutions to {OUT_DIR}")


if __name__ == "__main__":
    main()
