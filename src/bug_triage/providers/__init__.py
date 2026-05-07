"""Chat-provider Protocol with fake/Anthropic/OpenAI implementations."""

from bug_triage.providers.base import ChatMessage, ChatProvider, ChatResponse
from bug_triage.providers.fake import FakeProvider, build_provider

__all__ = ["ChatMessage", "ChatProvider", "ChatResponse", "FakeProvider", "build_provider"]
