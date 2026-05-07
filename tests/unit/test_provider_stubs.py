"""Real-provider stubs raise without API keys (BYOK contract)."""

from __future__ import annotations

import pytest


def test_anthropic_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from bug_triage.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_openai_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from bug_triage.providers.openai_provider import OpenAIProvider

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIProvider()
