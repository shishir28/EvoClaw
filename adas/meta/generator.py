"""Generates a candidate skill by calling meta_system.md + meta_design.md prompts."""

from __future__ import annotations

from pathlib import Path

try:
    from ..config import PROMPTS_DIR
    from ..evaluation.judge import ChatCompletionClient
    from .client import make_client
    from .models import Candidate, MetaContext
    from .parser import extract_candidate, parse_response
except ImportError:
    from config import PROMPTS_DIR
    from evaluation.judge import ChatCompletionClient
    from meta.client import make_client
    from meta.models import Candidate, MetaContext
    from meta.parser import extract_candidate, parse_response


class Generator:
    def __init__(
        self,
        client: ChatCompletionClient | None = None,
        prompt_dir: str = PROMPTS_DIR,
    ) -> None:
        """Accept an optional pre-built client so tests can inject a fake without
        touching the real LLM backend."""
        self._client = client or make_client()
        self._prompt_dir = Path(prompt_dir)

    def _load(self, name: str) -> str:
        """Read a prompt file by name from the configured prompts directory."""
        return (self._prompt_dir / name).read_text()

    def _build_user_prompt(self, context: MetaContext) -> str:
        """Substitute all MetaContext placeholders into meta_design.md to produce
        the user turn sent to the LLM."""
        return (
            self._load("meta_design.md")
            .replace("ARCHIVE_INDEX_JSON", context.archive_index_json)
            .replace("ARCHIVE_SKILL_SUMMARIES_JSON", context.archive_skill_summaries_json)
            .replace("BEST_SKILL_MD", context.best_skill_md)
            .replace("RECENT_FEEDBACK_SUMMARY_JSON", context.recent_feedback_summary_json)
            .replace("DESIGN_GOAL", context.design_goal)
        )

    def generate(self, context: MetaContext) -> Candidate:
        """Call the LLM and return a validated Candidate extracted from the response JSON."""
        system_prompt = self._load("meta_system.md")
        user_prompt = self._build_user_prompt(context)
        response = self._client.complete(system_prompt, user_prompt)
        return extract_candidate(parse_response(response))
