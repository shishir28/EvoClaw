"""
Builder and factory utilities shared across adas tests.

Design notes (SOLID):
- VideoRecordBuilder / SkillDocumentBuilder follow the Builder pattern so
  each test declares only the fields it cares about.
- FeedbackFactory is a Single-Responsibility factory for feedback history objects.
- Builders use a fluent API: each with_* returns self for chaining.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "adas"))

from evaluation.models import (
    DimensionScore,
    EvaluationRequest,
    EvaluationResult,
    FeedbackEntry,
    FeedbackPick,
    SkillDocument,
    VideoRecord,
)
from config import SCORE_WEIGHTS


# ---------------------------------------------------------------------------
# Time helper
# ---------------------------------------------------------------------------

def hours_ago(n: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=n)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# VideoRecordBuilder
# ---------------------------------------------------------------------------

class VideoRecordBuilder:
    """Fluent builder for VideoRecord test objects."""

    def __init__(self) -> None:
        self._video_id = "vid1"
        self._title = "How I Built an AI Startup"
        self._channel = "FounderCasts"
        self._channel_id = "ch1"
        self._published_hours_ago = 24.0
        self._views = 1000
        self._views_per_hour = 50.0
        self._subscriber_count: int | None = 50_000
        self._duration_seconds = 900
        self._description = "A practical guide to building an AI startup."
        self._transcript: str | None = None
        self._tags: list[str] = []
        self._thumbnail = ""
        self._query_matched = "AI startup 2026"

    def with_id(self, video_id: str) -> "VideoRecordBuilder":
        self._video_id = video_id
        return self

    def with_title(self, title: str) -> "VideoRecordBuilder":
        self._title = title
        return self

    def with_channel(self, channel: str, channel_id: str) -> "VideoRecordBuilder":
        self._channel = channel
        self._channel_id = channel_id
        return self

    def with_age_hours(self, hours: float) -> "VideoRecordBuilder":
        self._published_hours_ago = hours
        return self

    def with_views_per_hour(self, vph: float) -> "VideoRecordBuilder":
        self._views_per_hour = vph
        return self

    def with_subscriber_count(self, count: int | None) -> "VideoRecordBuilder":
        self._subscriber_count = count
        return self

    def with_duration_seconds(self, seconds: int) -> "VideoRecordBuilder":
        self._duration_seconds = seconds
        return self

    def with_description(self, description: str) -> "VideoRecordBuilder":
        self._description = description
        return self

    def with_transcript(self, transcript: str | None) -> "VideoRecordBuilder":
        self._transcript = transcript
        return self

    def with_tags(self, tags: list[str]) -> "VideoRecordBuilder":
        self._tags = tags
        return self

    def with_query_matched(self, query: str) -> "VideoRecordBuilder":
        self._query_matched = query
        return self

    def build(self) -> VideoRecord:
        return VideoRecord(
            video_id=self._video_id,
            title=self._title,
            channel=self._channel,
            channel_id=self._channel_id,
            published_at=hours_ago(self._published_hours_ago),
            views=self._views,
            likes=0,
            subscriber_count=self._subscriber_count,
            duration_seconds=self._duration_seconds,
            tags=self._tags,
            category_id="28",
            views_per_hour=self._views_per_hour,
            url=f"https://www.youtube.com/watch?v={self._video_id}",
            description=self._description,
            thumbnail=self._thumbnail,
            query_matched=self._query_matched,
            transcript=self._transcript,
        )


def video() -> VideoRecordBuilder:
    """Entry-point for the VideoRecord builder."""
    return VideoRecordBuilder()


# ---------------------------------------------------------------------------
# SkillDocumentBuilder
# ---------------------------------------------------------------------------

class SkillDocumentBuilder:
    """Fluent builder for SkillDocument test objects."""

    def __init__(self) -> None:
        self._name = "recency-first"
        self._strategy: str | None = "recency"
        self._description = "Pick newest AI startup videos."
        self._path = "/fake/SKILL.md"

    def with_name(self, name: str) -> "SkillDocumentBuilder":
        self._name = name
        return self

    def with_strategy(self, strategy: str | None) -> "SkillDocumentBuilder":
        self._strategy = strategy
        return self

    def with_description(self, description: str) -> "SkillDocumentBuilder":
        self._description = description
        return self

    def build(self) -> SkillDocument:
        return SkillDocument(
            path=self._path,
            raw_text="",
            body="",
            metadata={
                "name": self._name,
                "strategy": self._strategy or "",
                "description": self._description,
            },
            name=self._name,
            strategy=self._strategy,
            description=self._description,
        )


def skill() -> SkillDocumentBuilder:
    """Entry-point for the SkillDocument builder."""
    return SkillDocumentBuilder()


# ---------------------------------------------------------------------------
# FeedbackFactory
# ---------------------------------------------------------------------------

class FeedbackFactory:
    """Single-responsibility factory for FeedbackEntry lists."""

    @staticmethod
    def all_up(video_ids: list[str]) -> list[FeedbackEntry]:
        return [FeedbackEntry(
            date="2026-04-30",
            picks=[FeedbackPick(video_id=vid, reaction="up") for vid in video_ids],
        )]

    @staticmethod
    def all_down(video_ids: list[str]) -> list[FeedbackEntry]:
        return [FeedbackEntry(
            date="2026-04-30",
            picks=[FeedbackPick(video_id=vid, reaction="down") for vid in video_ids],
        )]

    @staticmethod
    def mixed(reactions: dict[str, str | None]) -> list[FeedbackEntry]:
        return [FeedbackEntry(
            date="2026-04-30",
            picks=[FeedbackPick(video_id=vid, reaction=r) for vid, r in reactions.items()],
        )]


# ---------------------------------------------------------------------------
# EvaluationRequest factory
# ---------------------------------------------------------------------------

def make_request(
    videos: list[VideoRecord] | None = None,
    skill_doc: SkillDocument | None = None,
    feedback_history: list[FeedbackEntry] | None = None,
) -> EvaluationRequest:
    return EvaluationRequest(
        skill=skill_doc or skill().build(),
        videos=videos or [video().build()],
        feedback_history=feedback_history or [],
        cache_path="/fake/cache.json",
        feedback_path=None,
    )


# ---------------------------------------------------------------------------
# EvaluationResult factory
# ---------------------------------------------------------------------------

def make_result(
    selected_video_ids: list[str] | None = None,
    score_weights: dict[str, float] | None = None,
) -> EvaluationResult:
    weights = score_weights or SCORE_WEIGHTS
    return EvaluationResult(
        skill_name="test-skill",
        strategy="recency",
        cache_path="/fake/cache.json",
        video_count=3,
        dimensions=[DimensionScore(name=n, weight=w) for n, w in weights.items()],
        selected_video_ids=selected_video_ids or [],
    )


def make_scored_result(skill_name: str, total_score: float) -> EvaluationResult:
    result = make_result()
    result.skill_name = skill_name
    result.total_score = total_score
    result.status = "scored"
    return result
