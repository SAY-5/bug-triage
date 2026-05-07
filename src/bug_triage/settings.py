"""Runtime configuration loaded from env vars."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration. Read once at startup."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    provider: str = Field(default="fake", description="fake | anthropic | openai")
    hash_embedder: bool = Field(default=True, alias="HASH_EMBEDDER")
    database_url: str = Field(
        default="postgresql+psycopg://bug_triage:bug_triage@localhost:5432/bug_triage",
        alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def corpus_root(self) -> Path:
        return self.repo_root / "corpus"

    @property
    def java_target_root(self) -> Path:
        return self.corpus_root / "target"


def get_settings() -> Settings:
    """Build a fresh ``Settings`` instance.

    Tests can monkeypatch env vars and call this again to get an updated view.
    """
    return Settings()
