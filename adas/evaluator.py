"""
Evaluator contracts and data loading for ADAS skill scoring.

This file defines the request/response shapes that later scoring logic will use.
It intentionally stops short of implementing full scoring so the contract can be
reviewed and stabilized before the evaluator behavior is built out.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import FEEDBACK_FILE, SCORE_WEIGHTS, TEST_SETS_DIR
from youtube_fetcher import YouTubeFetcher


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


@dataclass(slots=True)
class SkillDocument:
    path: str
    raw_text: str
    body: str
    metadata: dict[str, str] = field(default_factory=dict)
    name: str | None = None
    strategy: str | None = None
    version: str | None = None
    author: str | None = None
    description: str | None = None

    @classmethod
    def from_path(cls, path: str) -> "SkillDocument":
        resolved = Path(path)
        raw_text = resolved.read_text()
        metadata, body = _parse_frontmatter(raw_text)
        return cls(
            path=str(resolved),
            raw_text=raw_text,
            body=body,
            metadata=metadata,
            name=metadata.get("name"),
            strategy=metadata.get("strategy"),
            version=metadata.get("version"),
            author=metadata.get("author"),
            description=metadata.get("description"),
        )


@dataclass(slots=True)
class VideoRecord:
    video_id: str
    title: str
    channel: str
    channel_id: str
    published_at: str
    description: str
    thumbnail: str
    query_matched: str
    views: int = 0
    likes: int = 0
    subscriber_count: int | None = None
    duration_seconds: int = 0
    tags: list[str] = field(default_factory=list)
    category_id: str = ""
    views_per_hour: float = 0.0
    url: str = ""
    transcript: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VideoRecord":
        return cls(
            video_id=payload["video_id"],
            title=payload.get("title", ""),
            channel=payload.get("channel", ""),
            channel_id=payload.get("channel_id", ""),
            published_at=payload.get("published_at", ""),
            description=payload.get("description", ""),
            thumbnail=payload.get("thumbnail", ""),
            query_matched=payload.get("query_matched", ""),
            views=int(payload.get("views", 0) or 0),
            likes=int(payload.get("likes", 0) or 0),
            subscriber_count=(
                int(payload["subscriber_count"])
                if payload.get("subscriber_count") is not None
                else None
            ),
            duration_seconds=int(payload.get("duration_seconds", 0) or 0),
            tags=list(payload.get("tags", [])),
            category_id=payload.get("category_id", ""),
            views_per_hour=float(payload.get("views_per_hour", 0.0) or 0.0),
            url=payload.get("url", ""),
            transcript=payload.get("transcript"),
        )

    @property
    def transcript_or_description(self) -> str:
        return self.transcript or self.description


@dataclass(slots=True)
class FeedbackPick:
    video_id: str
    reaction: str | None
    skill_version: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackPick":
        return cls(
            video_id=payload["video_id"],
            reaction=payload.get("reaction"),
            skill_version=payload.get("skill_version"),
        )


@dataclass(slots=True)
class FeedbackEntry:
    date: str
    picks: list[FeedbackPick] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackEntry":
        return cls(
            date=payload.get("date", ""),
            picks=[FeedbackPick.from_dict(pick) for pick in payload.get("picks", [])],
        )


@dataclass(slots=True)
class EvaluationRequest:
    skill: SkillDocument
    videos: list[VideoRecord]
    feedback_history: list[FeedbackEntry]
    cache_path: str
    feedback_path: str | None

    @classmethod
    def from_paths(
        cls,
        skill_path: str,
        cache_path: str,
        feedback_path: str | None = FEEDBACK_FILE,
    ) -> "EvaluationRequest":
        skill = SkillDocument.from_path(skill_path)
        resolved_cache_path = _resolve_path(cache_path)
        videos = [
            VideoRecord.from_dict(video)
            for video in YouTubeFetcher.load_cache(str(resolved_cache_path))
        ]

        feedback_history: list[FeedbackEntry] = []
        resolved_feedback_path: Path | None = None
        if feedback_path:
            resolved_feedback_path = _resolve_path(feedback_path, base_dir="")
            if resolved_feedback_path.exists():
                raw_feedback = json.loads(resolved_feedback_path.read_text())
                history = raw_feedback.get("history", [])
                feedback_history = [FeedbackEntry.from_dict(entry) for entry in history]

        return cls(
            skill=skill,
            videos=videos,
            feedback_history=feedback_history,
            cache_path=str(resolved_cache_path),
            feedback_path=str(resolved_feedback_path) if resolved_feedback_path else None,
        )


@dataclass(slots=True)
class DimensionScore:
    name: str
    weight: float
    score: float | None = None
    detail: str = ""


@dataclass(slots=True)
class EvaluationResult:
    skill_name: str
    strategy: str | None
    cache_path: str
    video_count: int
    dimensions: list[DimensionScore]
    total_score: float | None = None
    status: str = "pending"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Evaluator:
    """Loads evaluator inputs and creates result scaffolding for future scoring."""

    def load_request(
        self,
        skill_path: str,
        cache_path: str,
        feedback_path: str | None = FEEDBACK_FILE,
    ) -> EvaluationRequest:
        return EvaluationRequest.from_paths(
            skill_path=skill_path,
            cache_path=cache_path,
            feedback_path=feedback_path,
        )

    def build_result_template(self, request: EvaluationRequest) -> EvaluationResult:
        dimensions = [
            DimensionScore(
                name=name,
                weight=weight,
                detail="Not scored yet.",
            )
            for name, weight in SCORE_WEIGHTS.items()
        ]
        return EvaluationResult(
            skill_name=request.skill.name or Path(request.skill.path).stem,
            strategy=request.skill.strategy,
            cache_path=request.cache_path,
            video_count=len(request.videos),
            dimensions=dimensions,
            notes=[
                "This is a contract-only result template.",
                "Scoring logic will be added in the next evaluator steps.",
            ],
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load evaluator inputs and print the contract.")
    parser.add_argument("--skill", required=True, help="Path to the candidate SKILL.md file")
    parser.add_argument("--cache", required=True, help="Path to a cached video JSON file")
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        help="Optional path to feedback JSON",
    )
    args = parser.parse_args()

    evaluator = Evaluator()
    request = evaluator.load_request(
        skill_path=args.skill,
        cache_path=args.cache,
        feedback_path=args.feedback,
    )
    result = evaluator.build_result_template(request)

    print(
        json.dumps(
            {
                "request": {
                    "skill_name": request.skill.name,
                    "strategy": request.skill.strategy,
                    "video_count": len(request.videos),
                    "feedback_entries": len(request.feedback_history),
                    "cache_path": request.cache_path,
                    "feedback_path": request.feedback_path,
                },
                "result_template": result.to_dict(),
            },
            indent=2,
        )
    )
