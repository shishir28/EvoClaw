"""Reflects on a candidate skill and returns a verdict with optional repairs."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from ..config import PROMPTS_DIR
    from ..evaluation.judge import ChatCompletionClient
    from .client import make_client
    from .models import Candidate, MetaContext, ReflectionResult
    from .parser import parse_reflection_response
except ImportError:
    from config import PROMPTS_DIR
    from evaluation.judge import ChatCompletionClient
    from meta.client import make_client
    from meta.models import Candidate, MetaContext, ReflectionResult
    from meta.parser import parse_reflection_response


class Reflector:
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

    def _build_user_prompt(self, candidate: Candidate, context: MetaContext) -> str:
        """Serialise the candidate to JSON and substitute it plus all archive/feedback
        context placeholders into meta_reflect.md."""
        candidate_json = json.dumps(
            {
                "thought": candidate.thought,
                "name": candidate.name,
                "skill_md": candidate.skill_md,
            },
            indent=2,
            ensure_ascii=False,
        )
        return (
            self._load("meta_reflect.md")
            .replace("CANDIDATE_JSON", candidate_json)
            .replace("ARCHIVE_INDEX_JSON", context.archive_index_json)
            .replace("ARCHIVE_SKILL_SUMMARIES_JSON", context.archive_skill_summaries_json)
            .replace("BEST_SKILL_MD", context.best_skill_md)
            .replace("RECENT_FEEDBACK_SUMMARY_JSON", context.recent_feedback_summary_json)
        )

    def reflect(self, candidate: Candidate, context: MetaContext) -> ReflectionResult:
        """Ask the LLM to accept or revise the candidate.
        Always returns a ReflectionResult with a (possibly-repaired) Candidate, even on revise."""
        system_prompt = self._load("meta_system.md")
        user_prompt = self._build_user_prompt(candidate, context)
        response = self._client.complete(system_prompt, user_prompt)
        parsed = parse_reflection_response(response)

        verdict = str(parsed.get("verdict", "revise"))
        if verdict not in ("accept", "revise"):
            verdict = "revise"

        issues = list(parsed.get("issues", []))
        checks = {str(k): bool(v) for k, v in parsed.get("checks", {}).items()}
        thought = str(parsed.get("thought", ""))

        # Extract possibly-repaired candidate inline with reflection response.
        name = str(parsed.get("name", candidate.name))
        skill_md = str(parsed.get("skill_md", candidate.skill_md))
        repaired = Candidate(thought=thought, name=name, skill_md=skill_md)

        return ReflectionResult(
            verdict=verdict,
            issues=issues,
            checks=checks,
            thought=thought,
            candidate=repaired,
        )
