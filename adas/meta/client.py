"""Thin chat-completion client wrapper for the meta-agent.

Reuses OpenAIChatCompletionClient from evaluation.judge rather than
duplicating transport logic.
"""

from __future__ import annotations

from adas.config import LLM_BASE_URL, LLM_MODEL
from adas.evaluation.judge import ChatCompletionClient, OpenAIChatCompletionClient


def make_client(
    base_url: str | None = None,
    model: str | None = None,
) -> ChatCompletionClient:
    """Return a chat client pointed at the active inference backend.
    Falls back to the env-configured LLM_BASE_URL and LLM_MODEL when not supplied."""
    return OpenAIChatCompletionClient(
        base_url=base_url or LLM_BASE_URL,
        model=model or LLM_MODEL,
    )
