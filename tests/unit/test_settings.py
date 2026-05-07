"""Settings env-var wiring."""

from __future__ import annotations

import pytest

from bug_triage.settings import get_settings


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("HASH_EMBEDDER", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_defaults() -> None:
    s = get_settings()
    assert s.provider == "fake"
    assert s.hash_embedder is True
    assert s.database_url.startswith("postgresql")
    assert s.corpus_root.name == "corpus"
    assert s.java_target_root.name == "target"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER", "openai")
    monkeypatch.setenv("HASH_EMBEDDER", "0")
    s = get_settings()
    assert s.provider == "openai"
    assert s.hash_embedder is False


def test_provider_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from bug_triage.providers import build_provider

    monkeypatch.setenv("PROVIDER", "fake")
    assert build_provider("fake").name == "fake"
    with pytest.raises(ValueError):
        build_provider("nope")
