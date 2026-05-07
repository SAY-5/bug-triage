"""OpenAI provider stub. BYOK; not exercised by CI."""

from __future__ import annotations

import os

from bug_triage.providers.base import ChatMessage, ChatResponse


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the openai provider")
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Install the providers extra: poetry install --with providers"
            ) from exc
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:  # pragma: no cover
        result = self._client.chat.completions.create(
            model=model or self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        text = result.choices[0].message.content or ""
        usage = result.usage
        return ChatResponse(
            text=text,
            tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
            cost_usd=0.0,
            model_version=str(result.model),
        )
