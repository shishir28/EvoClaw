"""
Algorithmic scoring for evaluator dimensions that do not require model calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from itertools import combinations

try:
    from evaluator_models import EvaluationRequest, VideoRecord
except ModuleNotFoundError:
    from adas.evaluator_models import EvaluationRequest, VideoRecord

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

def _extract_topic_terms(video: VideoRecord) -> set[str]:
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


class AlgorithmicScorer:
    def score_freshness(self, videos: list[VideoRecord]) -> tuple[float, str]:
        if not videos:
            raise ValueError("score_freshness requires at least one selected video.")

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
        if not videos:
            raise ValueError("score_diversity requires at least one selected video.")
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
        if not videos:
            raise ValueError("score_alignment_placeholder requires at least one selected video.")
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
