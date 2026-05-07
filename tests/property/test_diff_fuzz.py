"""Hypothesis fuzz tests for the suggester's diff validation path.

The suggester wraps unidiff.PatchSet and reports parse failures via
``_validate_diff``. This file fuzzes that boundary:

- random byte streams must never crash ``_validate_diff``; they must
  resolve to either (True, None) or (False, <reason>)
- syntactically valid unified diffs must always parse (True, None)
- ``_parse_or_empty`` must never raise on arbitrary text input
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bug_triage.suggester import _parse_or_empty, _validate_diff


@given(payload=st.binary(min_size=0, max_size=4096))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_validate_diff_never_crashes(payload: bytes) -> None:
    text = payload.decode("utf-8", errors="replace")
    parses, err = _validate_diff(text)
    assert isinstance(parses, bool)
    if parses:
        assert err is None
    else:
        assert err is None or isinstance(err, str)


@given(
    text=st.text(
        alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
        min_size=0,
        max_size=2048,
    )
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_validate_diff_text_never_crashes(text: str) -> None:
    parses, err = _validate_diff(text)
    assert isinstance(parses, bool)
    assert err is None or isinstance(err, str)


@st.composite
def synthetic_unified_diff(draw: st.DrawFn) -> str:
    file_path = draw(
        st.sampled_from(
            [
                "src/main/java/com/example/calc/Calculator.java",
                "src/main/java/com/example/calc/ExpressionParser.java",
                "src/main/java/com/example/calc/Validation.java",
            ]
        )
    )
    before = draw(
        st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
            min_size=1,
            max_size=80,
        ).filter(lambda s: not s.startswith("+") and not s.startswith("-"))
    )
    after = draw(
        st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
            min_size=1,
            max_size=80,
        ).filter(lambda s: not s.startswith("+") and not s.startswith("-"))
    )
    context_line = " // context"
    return (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f"{context_line}\n"
        f"-{before}\n"
        f"+{after}\n"
    )


@given(diff=synthetic_unified_diff())
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_synthetic_valid_diffs_parse(diff: str) -> None:
    parses, err = _validate_diff(diff)
    assert parses, f"valid diff failed to parse: err={err!r} diff={diff!r}"
    assert err is None


@given(raw=st.binary(min_size=0, max_size=2048))
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_parse_or_empty_never_crashes_on_bytes(raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    output, original = _parse_or_empty(text)
    assert original == text
    assert 0.0 <= output.confidence <= 1.0
