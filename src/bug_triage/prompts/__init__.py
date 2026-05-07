"""Versioned prompt templates loaded from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    user_template: str

    def render(self, **kwargs: object) -> str:
        return self.user_template.format(**kwargs)


@lru_cache(maxsize=8)
def load(name: str) -> PromptTemplate:
    path = PROMPTS_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptTemplate(
        name=name,
        version=str(data["version"]),
        system=str(data["system"]),
        user_template=str(data["user"]),
    )
