"""
Evaluator contracts and data loading for ADAS skill scoring.

This file defines the request/response shapes that later scoring logic will use.
It intentionally stops short of implementing full scoring so the contract can be
reviewed and stabilized before the evaluator behavior is built out.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

try:
    from config import FEEDBACK_FILE, SCORE_WEIGHTS, TEST_SETS_DIR
    from skill_executor import BaselineSkillExecutor
    from youtube_fetcher import YouTubeFetcher
except ModuleNotFoundError:
    from adas.config import FEEDBACK_FILE, SCORE_WEIGHTS, TEST_SETS_DIR
    from adas.skill_executor import BaselineSkillExecutor
    from adas.youtube_fetcher import YouTubeFetcher


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


_GENERIC_TOPIC_TERMS = {
    "about",
    "advice",
    "agent",
    "agents",
    "artificial",
    "best",
    "business",
    "company",
    "content",
    "entrepreneur",
    "entrepreneurship",
    "founder",
    "founders",
    "future",
    "gpt",
    "guide",
    "howto",
    "ideas",
    "insights",
    "intelligence",
    "launch",
    "latest",
    "learn",
    "learning",
    "llm",
    "machine",
    "money",
    "news",
    "podcast",
    "product",
    "products",
    "saas",
    "startup",
    "startups",
    "story",
    "strategy",
    "tech",
    "tips",
    "tools",
    "video",
    "watch",
}


def _normalize_reaction(reaction: str | None) -> float:
    if reaction is None:
        return 5.0

    normalized = reaction.strip().lower()
    if normalized in {"up", "thumbs_up", "like", "liked", "positive", "👍"}:
        return 10.0
    if normalized in {"down", "thumbs_down", "dislike", "disliked", "negative", "👎"}:
        return 0.0
    return 5.0


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _age_hours(published_at: str) -> float:
    return max(
        (_parse_timestamp(published_at) - datetime.now(timezone.utc)).total_seconds() / -3600,
        0.0,
    )


def _extract_topic_terms(video: "VideoRecord") -> set[str]:
    source = " ".join(
        [
            video.title,
            video.description,
            video.query_matched,
            " ".join(video.tags),
        ]
    ).lower()
    tokens = re.findall(r"[a-z0-9]+", source)
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in _GENERIC_TOPIC_TERMS
    }


def _pairwise_jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


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
    selected_video_ids: list[str] = field(default_factory=list)
    total_score: float | None = None
    status: str = "pending"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def dimension_map(self) -> dict[str, DimensionScore]:
        return {dimension.name: dimension for dimension in self.dimensions}


class Evaluator:
    """Loads evaluator inputs and creates result scaffolding for future scoring."""

    def __init__(self) -> None:
        self._skill_executor = BaselineSkillExecutor()

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
                "Scoring logic is still in progress.",
                "Weighted aggregation is available once dimension scores are assigned.",
            ],
        )

    def resolve_selected_videos(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str],
    ) -> list[VideoRecord]:
        if not selected_video_ids:
            raise ValueError("selected_video_ids must contain at least one video ID.")

        if len(selected_video_ids) != len(set(selected_video_ids)):
            raise ValueError("selected_video_ids must not contain duplicates.")

        videos_by_id = {video.video_id: video for video in request.videos}
        missing_video_ids = [
            video_id for video_id in selected_video_ids if video_id not in videos_by_id
        ]
        if missing_video_ids:
            raise ValueError(
                "Selected video IDs not found in cache: " + ", ".join(missing_video_ids)
            )

        return [videos_by_id[video_id] for video_id in selected_video_ids]

    def apply_dimension_scores(
        self,
        result: EvaluationResult,
        scores: dict[str, float],
        details: dict[str, str] | None = None,
    ) -> EvaluationResult:
        details = details or {}
        dimension_map = result.dimension_map()

        unexpected_dimensions = sorted(set(scores) - set(dimension_map))
        if unexpected_dimensions:
            raise ValueError(
                f"Unknown dimension score(s): {', '.join(unexpected_dimensions)}"
            )
        unexpected_detail_dimensions = sorted(set(details) - set(dimension_map))
        if unexpected_detail_dimensions:
            raise ValueError(
                f"Unknown dimension detail(s): {', '.join(unexpected_detail_dimensions)}"
            )

        for name, detail in details.items():
            dimension_map[name].detail = detail

        for name, score in scores.items():
            if not 0.0 <= score <= 10.0:
                raise ValueError(f"Score for '{name}' must be between 0 and 10.")
            dimension_map[name].score = round(float(score), 4)

        return result

    def aggregate_weighted_score(self, result: EvaluationResult) -> EvaluationResult:
        dimension_map = result.dimension_map()
        expected_dimensions = set(SCORE_WEIGHTS)
        actual_dimensions = set(dimension_map)

        missing_dimensions = sorted(expected_dimensions - actual_dimensions)
        unexpected_dimensions = sorted(actual_dimensions - expected_dimensions)
        if missing_dimensions or unexpected_dimensions:
            problems: list[str] = []
            if missing_dimensions:
                problems.append(f"missing dimensions: {', '.join(missing_dimensions)}")
            if unexpected_dimensions:
                problems.append(
                    f"unexpected dimensions: {', '.join(unexpected_dimensions)}"
                )
            raise ValueError("Cannot aggregate result with mismatched dimensions: " + "; ".join(problems))

        total_weight = sum(dimension.weight for dimension in result.dimensions)
        if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"Dimension weights must sum to 1.0, got {total_weight}.")

        missing_scores = sorted(
            dimension.name
            for dimension in result.dimensions
            if dimension.score is None
        )
        if missing_scores:
            raise ValueError(
                "Cannot aggregate weighted score without values for: "
                + ", ".join(missing_scores)
            )

        weighted_total = sum(
            dimension.weight * float(dimension.score)
            for dimension in result.dimensions
        )
        result.total_score = round(weighted_total, 4)
        result.status = "scored"
        return result

    def score_freshness(self, videos: list[VideoRecord]) -> tuple[float, str]:
        per_video_scores: list[tuple[str, float, float]] = []
        for video in videos:
            age_hours = _age_hours(video.published_at)
            base_score = 6.0 if age_hours <= 168 else max(0.0, 6.0 * (720 - age_hours) / 552)
            bonus = max(0.0, 4.0 * (48 - min(age_hours, 48.0)) / 48.0)
            score = min(10.0, base_score + bonus)
            per_video_scores.append((video.video_id, round(age_hours, 2), score))

        average_score = round(
            sum(score for _, _, score in per_video_scores) / len(per_video_scores),
            4,
        )
        detail = "; ".join(
            f"{video_id}: {hours}h old -> {round(score, 2)}"
            for video_id, hours, score in per_video_scores
        )
        return average_score, detail

    def score_diversity(self, videos: list[VideoRecord]) -> tuple[float, str]:
        if len(videos) == 1:
            return 10.0, "Only one selected video; diversity defaults to 10.0."

        unique_channels = len({video.channel_id for video in videos})
        channel_score = 10.0 * (unique_channels - 1) / (len(videos) - 1)

        topic_terms = {video.video_id: _extract_topic_terms(video) for video in videos}
        pairwise_similarity = [
            _pairwise_jaccard(topic_terms[left.video_id], topic_terms[right.video_id])
            for left, right in combinations(videos, 2)
        ]
        average_similarity = (
            sum(pairwise_similarity) / len(pairwise_similarity)
            if pairwise_similarity
            else 0.0
        )
        topical_score = 10.0 * (1.0 - average_similarity)
        diversity_score = round((channel_score + topical_score) / 2.0, 4)
        detail = (
            f"{unique_channels}/{len(videos)} unique channels; "
            f"avg topical similarity={round(average_similarity, 4)}"
        )
        return diversity_score, detail

    def score_alignment_placeholder(
        self,
        request: EvaluationRequest,
        videos: list[VideoRecord],
    ) -> tuple[float, str]:
        if not request.feedback_history:
            return 5.0, "No feedback history yet; using neutral placeholder score."

        feedback_by_video: dict[str, list[float]] = {}
        for entry in request.feedback_history:
            for pick in entry.picks:
                feedback_by_video.setdefault(pick.video_id, []).append(
                    _normalize_reaction(pick.reaction)
                )

        per_video_scores: list[tuple[str, float, str]] = []
        for video in videos:
            historical_scores = feedback_by_video.get(video.video_id)
            if historical_scores:
                score = sum(historical_scores) / len(historical_scores)
                source = "historical"
            else:
                score = 5.0
                source = "neutral"
            per_video_scores.append((video.video_id, score, source))

        alignment_score = round(
            sum(score for _, score, _ in per_video_scores) / len(per_video_scores),
            4,
        )
        detail = "; ".join(
            f"{video_id}: {round(score, 2)} ({source})"
            for video_id, score, source in per_video_scores
        )
        return alignment_score, detail

    def score_algorithmic_dimensions(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str],
    ) -> EvaluationResult:
        selected_videos = self.resolve_selected_videos(request, selected_video_ids)
        result = self.build_result_template(request)
        result.selected_video_ids = selected_video_ids

        freshness_score, freshness_detail = self.score_freshness(selected_videos)
        diversity_score, diversity_detail = self.score_diversity(selected_videos)
        alignment_score, alignment_detail = self.score_alignment_placeholder(
            request,
            selected_videos,
        )

        self.apply_dimension_scores(
            result,
            {
                "freshness": freshness_score,
                "diversity": diversity_score,
                "alignment": alignment_score,
            },
            details={
                "freshness": freshness_detail,
                "diversity": diversity_detail,
                "alignment": alignment_detail,
                "relevance": "Pending LLM judge.",
                "substance": "Pending LLM judge.",
                "reasoning": "Pending LLM judge.",
            },
        )

        result.status = "partially_scored"
        if len(selected_video_ids) != 3:
            result.notes.append(
                f"Expected 3 selected videos for production scoring, got {len(selected_video_ids)}."
            )
        result.notes.append(
            "Only algorithmic dimensions are scored here; LLM-judged dimensions remain pending."
        )
        return result

    def pending_dimension_names(self, result: EvaluationResult) -> list[str]:
        return [
            dimension.name
            for dimension in result.dimensions
            if dimension.score is None
        ]

    def score(
        self,
        skill_path: str,
        cache_path: str,
        selected_video_ids: list[str] | None = None,
        feedback_path: str | None = FEEDBACK_FILE,
        extra_scores: dict[str, float] | None = None,
        extra_details: dict[str, str] | None = None,
    ) -> EvaluationResult:
        """Orchestrate the currently supported evaluator flow.

        This method loads the request, computes algorithmic dimensions for the
        provided selected video IDs, optionally applies additional dimension
        scores (for example future LLM-judged dimensions), and aggregates the
        total once all dimensions are present.
        """
        request = self.load_request(
            skill_path=skill_path,
            cache_path=cache_path,
            feedback_path=feedback_path,
        )
        if selected_video_ids is None:
            execution = self._skill_executor.execute(request.skill, request.videos)
            selected_video_ids = execution.selected_video_ids
        else:
            execution = None

        result = self.score_algorithmic_dimensions(request, selected_video_ids)
        if execution:
            result.notes.extend(execution.notes)

        if extra_scores or extra_details:
            self.apply_dimension_scores(
                result,
                extra_scores or {},
                details=extra_details,
            )

        pending_dimensions = self.pending_dimension_names(result)
        if pending_dimensions:
            result.status = "partially_scored"
            result.notes.append(
                "Pending dimensions: " + ", ".join(pending_dimensions)
            )
            return result

        return self.aggregate_weighted_score(result)


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
    parser.add_argument(
        "--selected-ids",
        help="Comma-separated selected video IDs for algorithmic scoring",
    )
    parser.add_argument(
        "--extra-scores-json",
        help="Optional JSON object with additional dimension scores",
    )
    parser.add_argument(
        "--extra-details-json",
        help="Optional JSON object with additional dimension details",
    )
    args = parser.parse_args()

    evaluator = Evaluator()
    request = evaluator.load_request(
        skill_path=args.skill,
        cache_path=args.cache,
        feedback_path=args.feedback,
    )
    result = evaluator.build_result_template(request)
    if args.selected_ids:
        selected_video_ids = [
            video_id.strip() for video_id in args.selected_ids.split(",") if video_id.strip()
        ]
        extra_scores = json.loads(args.extra_scores_json) if args.extra_scores_json else None
        extra_details = json.loads(args.extra_details_json) if args.extra_details_json else None
        result = evaluator.score(
            skill_path=args.skill,
            cache_path=args.cache,
            selected_video_ids=selected_video_ids,
            feedback_path=args.feedback,
            extra_scores=extra_scores,
            extra_details=extra_details,
        )

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
