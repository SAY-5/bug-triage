"""Provider Protocol and shared message types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ChatResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_version: str


@runtime_checkable
class ChatProvider(Protocol):
    """Minimal chat completion surface. Synchronous; one shot per call."""

    name: str

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse: ...
