"""
Baseline skill execution adapter for evaluator use.

This is a Python-side stand-in for future OpenClaw execution. It understands the
current baseline-style `SKILL.md` strategies and deterministically picks videos
from a cached dataset so the evaluator can run end to end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


_AI_TERMS = {
    "ai",
    "artificial intelligence",
    "machine learning",
    "llm",
    "gpt",
    "agent",
    "agents",
    "claude",
    "agi",
    "openai",
}

_BUSINESS_TERMS = {
    "startup",
    "startups",
    "founder",
    "founders",
    "entrepreneur",
    "entrepreneurship",
    "saas",
    "venture",
    "funding",
    "business",
    "product",
    "products",
}

_BLOCKED_SCRIPT_RANGES = [
    ("\u0600", "\u06ff"),  # Arabic
    ("\u0900", "\u097f"),  # Devanagari
    ("\u0c00", "\u0c7f"),  # Telugu
    ("\u4e00", "\u9fff"),  # CJK Unified Ideographs
]


def _text(video: Any) -> str:
    return " ".join(
        [
            getattr(video, "title", ""),
            getattr(video, "description", ""),
            " ".join(getattr(video, "tags", []) or []),
            getattr(video, "query_matched", ""),
        ]
    ).lower()


def _contains_blocked_script(text: str) -> bool:
    return any(start <= ch <= end for ch in text for start, end in _BLOCKED_SCRIPT_RANGES)


def _looks_english(video: Any) -> bool:
    source = " ".join([getattr(video, "title", ""), getattr(video, "description", "")])
    if _contains_blocked_script(source):
        return False
    ascii_chars = sum(1 for ch in source if ord(ch) < 128 and ch.isalpha())
    alpha_chars = sum(1 for ch in source if ch.isalpha())
    if alpha_chars == 0:
        return True
    return ascii_chars / alpha_chars >= 0.85


def _is_relevant(video: Any) -> bool:
    source = _text(video)
    return any(term in source for term in _AI_TERMS) and any(
        term in source for term in _BUSINESS_TERMS
    )


def _published_at(video: Any) -> datetime:
    return datetime.fromisoformat(getattr(video, "published_at").replace("Z", "+00:00"))


def _age_hours(video: Any) -> float:
    return max(
        (datetime.now(timezone.utc) - _published_at(video)).total_seconds() / 3600,
        0.0,
    )


def _minutes(video: Any) -> float:
    return max(float(getattr(video, "duration_seconds", 0) or 0) / 60.0, 0.0)


def _subscriber_floor(video: Any, threshold: int) -> bool:
    subscriber_count = getattr(video, "subscriber_count", None)
    return subscriber_count is None or subscriber_count >= threshold


def _transcript_bonus(video: Any) -> float:
    transcript = getattr(video, "transcript", None) or ""
    return min(len(transcript) / 500.0, 4.0)


def _description_bonus(video: Any) -> float:
    description = getattr(video, "description", "") or ""
    return min(len(description) / 150.0, 3.0)


def _duration_bonus(video: Any) -> float:
    minutes = _minutes(video)
    if 4.0 <= minutes <= 45.0:
        return 2.0
    if 2.0 <= minutes < 4.0 or 45.0 < minutes <= 75.0:
        return 1.0
    return 0.0


def _short_penalty(video: Any) -> float:
    return 2.0 if _minutes(video) < 1.0 else 0.0


@dataclass(slots=True)
class SkillExecutionResult:
    selected_video_ids: list[str]
    notes: list[str] = field(default_factory=list)


class BaselineSkillExecutor:
    """Executes the current baseline strategies over cached video records."""

    def execute(self, skill: Any, videos: list[Any]) -> SkillExecutionResult:
        strategy = getattr(skill, "strategy", None)
        if strategy == "recency":
            return self._execute_recency(videos)
        if strategy == "engagement-velocity":
            return self._execute_engagement_velocity(videos)
        if strategy == "llm-substance-judge":
            return self._execute_substance_proxy(videos)
        raise ValueError(
            f"Unsupported skill strategy '{strategy}'. Add an adapter or use explicit selected IDs."
        )

    def _base_candidates(self, videos: list[Any]) -> list[Any]:
        return [
            video
            for video in videos
            if _looks_english(video) and _is_relevant(video)
        ]

    def _execute_recency(self, videos: list[Any]) -> SkillExecutionResult:
        candidates = [
            video for video in self._base_candidates(videos) if _subscriber_floor(video, 1000)
        ]
        recent_candidates = [video for video in candidates if _age_hours(video) <= 48.0]
        pool = recent_candidates if len(recent_candidates) >= 3 else candidates
        selected = sorted(pool, key=_published_at, reverse=True)[:3]
        notes = [
            "Executed recency strategy adapter.",
            f"Selected from {'48h window' if pool is recent_candidates else '7d fallback pool'}.",
        ]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=notes,
        )

    def _execute_engagement_velocity(self, videos: list[Any]) -> SkillExecutionResult:
        candidates = self._base_candidates(videos)
        primary_pool = [
            video for video in candidates if _subscriber_floor(video, 10000)
        ]
        pool = primary_pool
        if len(pool) < 3:
            pool = [video for video in candidates if _subscriber_floor(video, 1000)]
        selected = sorted(
            pool,
            key=lambda video: (getattr(video, "views_per_hour", 0.0), _published_at(video)),
            reverse=True,
        )[:3]
        notes = [
            "Executed engagement-velocity strategy adapter.",
            f"Used subscriber threshold {'10,000' if pool is primary_pool else '1,000 fallback'}.",
        ]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=notes,
        )

    def _execute_substance_proxy(self, videos: list[Any]) -> SkillExecutionResult:
        candidates = self._base_candidates(videos)
        ranked = sorted(
            candidates,
            key=lambda video: (
                _transcript_bonus(video)
                + _description_bonus(video)
                + _duration_bonus(video)
                - _short_penalty(video),
                getattr(video, "views_per_hour", 0.0),
            ),
            reverse=True,
        )
        selected = ranked[:3]
        notes = [
            "Executed substance-judge proxy adapter.",
            "Used transcript availability, description richness, and duration as substance heuristics.",
        ]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=notes,
        )
