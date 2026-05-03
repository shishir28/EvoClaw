"""
Loading services for evaluator request inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from ..config import FEEDBACK_FILE, TEST_SETS_DIR
    from ..youtube_fetcher import VideoCacheRepository
    from .models import EvaluationRequest, FeedbackEntry, SkillDocument, VideoRecord
except ImportError:
    from config import FEEDBACK_FILE, TEST_SETS_DIR
    from youtube_fetcher import VideoCacheRepository
    from evaluation.models import EvaluationRequest, FeedbackEntry, SkillDocument, VideoRecord


def _resolve_path(path: str, base_dir: str | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if base_dir is None:
        return Path(TEST_SETS_DIR) / candidate
    return Path(base_dir) / candidate


def _parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown

    parts = markdown.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, markdown

    raw_frontmatter = parts[0].removeprefix("---\n")
    body = parts[1]
    metadata: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')

    return metadata, body


class EvaluationRequestLoader:
    def __init__(self, cache_repository: VideoCacheRepository | None = None) -> None:
        self._cache_repository = cache_repository or VideoCacheRepository()

    def load_request(
        self,
        skill_path: str,
        cache_path: str,
        feedback_path: str | None = FEEDBACK_FILE,
    ) -> EvaluationRequest:
        skill = self.load_skill(skill_path)
        resolved_cache_path = _resolve_path(cache_path)
        videos = [
            VideoRecord.from_dict(video)
            for video in self._cache_repository.load(str(resolved_cache_path))
        ]

        resolved_feedback_path: Path | None = None
        feedback_history: list[FeedbackEntry] = []
        if feedback_path:
            resolved_feedback_path = _resolve_path(feedback_path)
            feedback_history = self.load_feedback_history(str(resolved_feedback_path))

        return EvaluationRequest(
            skill=skill,
            videos=videos,
            feedback_history=feedback_history,
            cache_path=str(resolved_cache_path),
            feedback_path=str(resolved_feedback_path) if resolved_feedback_path else None,
        )

    def load_skill(self, skill_path: str) -> SkillDocument:
        resolved = Path(skill_path)
        raw_text = resolved.read_text()
        metadata, body = _parse_frontmatter(raw_text)
        return SkillDocument.from_markdown(str(resolved), raw_text, body, metadata)

    def load_feedback_history(self, feedback_path: str) -> list[FeedbackEntry]:
        resolved = Path(feedback_path)
        if not resolved.exists():
            return []

        raw_feedback = json.loads(resolved.read_text())
        history = raw_feedback.get("history", [])
        return [FeedbackEntry.from_dict(entry) for entry in history]
