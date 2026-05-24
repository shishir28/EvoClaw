"""
Evaluator data contracts and loading models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    def from_markdown(
        cls,
        path: str,
        raw_text: str,
        body: str,
        metadata: dict[str, str],
    ) -> "SkillDocument":
        return cls(
            path=path,
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
    default_language: str = ""
    default_audio_language: str = ""
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
            default_language=payload.get("default_language", ""),
            default_audio_language=payload.get("default_audio_language", ""),
            views_per_hour=float(payload.get("views_per_hour", 0.0) or 0.0),
            url=payload.get("url", ""),
            transcript=payload.get("transcript"),
        )

    @property
    def transcript_or_description(self) -> str:
        return self.transcript or self.description

    @property
    def has_transcript(self) -> bool:
        return bool(self.transcript)

    @property
    def content_source(self) -> str:
        return "transcript" if self.has_transcript else "description"


@dataclass(slots=True)
class FeedbackVideoSnapshot:
    title: str
    channel: str
    channel_id: str
    published_at: str
    description: str
    query_matched: str
    duration_seconds: int = 0
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackVideoSnapshot":
        return cls(
            title=payload.get("title", ""),
            channel=payload.get("channel", ""),
            channel_id=payload.get("channel_id", ""),
            published_at=payload.get("published_at", ""),
            description=payload.get("description", ""),
            query_matched=payload.get("query_matched", ""),
            duration_seconds=int(payload.get("duration_seconds", 0) or 0),
            tags=list(payload.get("tags", [])),
        )

    @classmethod
    def from_video(cls, video: VideoRecord) -> "FeedbackVideoSnapshot":
        return cls(
            title=video.title,
            channel=video.channel,
            channel_id=video.channel_id,
            published_at=video.published_at,
            description=video.description,
            query_matched=video.query_matched,
            duration_seconds=video.duration_seconds,
            tags=list(video.tags),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FeedbackPick:
    video_id: str
    reaction: str | None
    skill_version: str | None = None
    snapshot: FeedbackVideoSnapshot | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackPick":
        return cls(
            video_id=payload["video_id"],
            reaction=payload.get("reaction"),
            skill_version=payload.get("skill_version"),
            snapshot=(
                FeedbackVideoSnapshot.from_dict(payload["snapshot"])
                if isinstance(payload.get("snapshot"), dict)
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        # snapshot is omitted when None so legacy feedback files without
        # a snapshot key round-trip cleanly through from_dict / to_dict.
        payload: dict[str, Any] = {
            "video_id": self.video_id,
            "reaction": self.reaction,
            "skill_version": self.skill_version,
        }
        if self.snapshot is not None:
            payload["snapshot"] = self.snapshot.to_dict()
        return payload


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "picks": [pick.to_dict() for pick in self.picks],
        }


@dataclass(slots=True)
class EvaluationRequest:
    skill: SkillDocument
    videos: list[VideoRecord]
    feedback_history: list[FeedbackEntry]
    cache_path: str
    feedback_path: str | None


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
