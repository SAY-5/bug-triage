"""Anthropic provider stub. BYOK; not exercised by CI."""

from __future__ import annotations

import os

from bug_triage.providers.base import ChatMessage, ChatResponse


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = "claude-3-5-sonnet-latest") -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the anthropic provider")
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Install the providers extra: poetry install --with providers"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def chat(self, messages: list[ChatMessage], *, model: str) -> ChatResponse:  # pragma: no cover
        system = next((m.content for m in messages if m.role == "system"), None)
        non_system = [m for m in messages if m.role != "system"]
        result = self._client.messages.create(
            model=model or self._model,
            max_tokens=2048,
            system=system or "",
            messages=[{"role": m.role, "content": m.content} for m in non_system],
        )
        text_block = next((b for b in result.content if getattr(b, "type", None) == "text"), None)
        text = getattr(text_block, "text", "") if text_block else ""
        usage = getattr(result, "usage", None)
        return ChatResponse(
            text=text,
            tokens_in=getattr(usage, "input_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "output_tokens", 0) if usage else 0,
            cost_usd=0.0,
            model_version=str(getattr(result, "model", model)),
        )
