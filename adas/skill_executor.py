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
from typing import Protocol

try:
    from evaluator_models import SkillDocument, VideoRecord
except ModuleNotFoundError:
    from adas.evaluator_models import SkillDocument, VideoRecord


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
    ("\u0600", "\u06ff"),
    ("\u0900", "\u097f"),
    ("\u0c00", "\u0c7f"),
    ("\u4e00", "\u9fff"),
]


def _text(video: VideoRecord) -> str:
    # Concatenates title + description + tags + query into one lowercase string for matching
    return " ".join(
        [
            video.title,
            video.description,
            " ".join(video.tags),
            video.query_matched,
        ]
    ).lower()


def _contains_blocked_script(text: str) -> bool:
    return any(
        start <= ch <= end for ch in text for start, end in _BLOCKED_SCRIPT_RANGES
    )


def _looks_english(video: VideoRecord) -> bool:
    # Rejects videos with Arabic/Hindi/Chinese/Telugu script, requires ≥85% ASCII alpha chars
    source = " ".join([video.title, video.description])
    if _contains_blocked_script(source):
        return False
    ascii_chars = sum(1 for ch in source if ord(ch) < 128 and ch.isalpha())
    alpha_chars = sum(1 for ch in source if ch.isalpha())
    if alpha_chars == 0:
        return True
    return ascii_chars / alpha_chars >= 0.85


def _term_matches(term: str, source: str) -> bool:
    return bool(re.search(r"\b" + re.escape(term) + r"\b", source))


def _is_relevant(video: VideoRecord) -> bool:
    # Requires at least one AI term AND one business term (whole-word regex match)
    source = _text(video)
    return any(_term_matches(term, source) for term in _AI_TERMS) and any(
        _term_matches(term, source) for term in _BUSINESS_TERMS
    )


def _published_at(video: VideoRecord) -> datetime:
    return datetime.fromisoformat(video.published_at.replace("Z", "+00:00"))


def _age_hours(video: VideoRecord) -> float:
    # Used by recency — filters to 48h window
    return max(
        (datetime.now(timezone.utc) - _published_at(video)).total_seconds() / 3600, 0.0
    )


def _minutes(video: VideoRecord) -> float:
    return max(float(video.duration_seconds or 0) / 60.0, 0.0)


def _subscriber_floor(video: VideoRecord, threshold: int) -> bool:
    # Used by recency ,  engagement-velocity — minimum subscriber gates
    return video.subscriber_count is None or video.subscriber_count >= threshold


def _transcript_bonus(video: VideoRecord) -> float:
    return min(len(video.transcript or "") / 500.0, 4.0)


def _description_bonus(video: VideoRecord) -> float:
    return min(len(video.description or "") / 150.0, 3.0)


def _duration_bonus(video: VideoRecord) -> float:
    minutes = _minutes(video)
    if 4.0 <= minutes <= 45.0:
        return 2.0
    if 2.0 <= minutes < 4.0 or 45.0 < minutes <= 75.0:
        return 1.0
    return 0.0


def _short_penalty(video: VideoRecord) -> float:
    return 2.0 if _minutes(video) < 1.0 else 0.0


@dataclass(slots=True)
class SkillExecutionResult:
    selected_video_ids: list[str]
    notes: list[str] = field(default_factory=list)


class SkillStrategyExecutor(Protocol):
    strategy_name: str

    def execute(self, videos: list[VideoRecord]) -> SkillExecutionResult: ...


class _BaseStrategyExecutor:
    def base_candidates(self, videos: list[VideoRecord]) -> list[VideoRecord]:
        # keeps only: _looks_english AND _is_relevant
        return [
            video for video in videos if _looks_english(video) and _is_relevant(video)
        ]


class RecencyStrategyExecutor(_BaseStrategyExecutor):
    strategy_name = "recency"

    def execute(self, videos: list[VideoRecord]) -> SkillExecutionResult:
        # filter subscriber >= 1000
        candidates = [
            video
            for video in self.base_candidates(videos)
            if _subscriber_floor(video, 1000)
        ]
        # prefer videos ≤ 48h old (fall back to full 7d pool if < 3 results
        recent_candidates = [video for video in candidates if _age_hours(video) <= 48.0]
        pool = recent_candidates if len(recent_candidates) >= 3 else candidates
        # sort by published_at DESC → top 3
        selected = sorted(pool, key=_published_at, reverse=True)[:3]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=[
                "Executed recency strategy adapter.",
                f"Selected from {'48h window' if pool is recent_candidates else '7d fallback pool'}.",
            ],
        )


class EngagementVelocityStrategyExecutor(_BaseStrategyExecutor):
    strategy_name = "engagement-velocity"

    def execute(self, videos: list[VideoRecord]) -> SkillExecutionResult:
        candidates = self.base_candidates(videos)
        primary_pool = [
            video for video in candidates if _subscriber_floor(video, 10000)
        ]
        # prefer subscriber >= 10,000 (fall back to 1,000 if < 3)
        pool = primary_pool
        if len(pool) < 3:
            pool = [video for video in candidates if _subscriber_floor(video, 1000)]
        # sort by (views_per_hour, published_at) DESC → top 3
        selected = sorted(
            pool,
            key=lambda video: (video.views_per_hour, _published_at(video)),
            reverse=True,
        )[:3]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=[
                "Executed engagement-velocity strategy adapter.",
                f"Used subscriber threshold {'10,000' if pool is primary_pool else '1,000 fallback'}.",
            ],
        )


class SubstanceProxyStrategyExecutor(_BaseStrategyExecutor):
    strategy_name = "llm-substance-judge"

    def execute(self, videos: list[VideoRecord]) -> SkillExecutionResult:
        # score each video: transcript_bonus + description_bonus + duration_bonus - short_penalty
        # → tiebreak by views_per_hour
        ranked = sorted(
            self.base_candidates(videos),
            key=lambda video: (
                _transcript_bonus(video)
                + _description_bonus(video)
                + _duration_bonus(video)
                - _short_penalty(video),
                video.views_per_hour,
            ),
            reverse=True,
        )
        # sort DESC → top 3
        selected = ranked[:3]
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=[
                "Executed substance-judge proxy adapter.",
                "Used transcript availability, description richness, and duration as substance heuristics.",
            ],
        )


class BaselineSkillExecutor:
    """Executes the current baseline strategies over cached video records."""

    def __init__(self, strategies: list[SkillStrategyExecutor] | None = None) -> None:
        # builds a dict: { "recency": executor, "engagement-velocity": executor, ... }
        strategy_list = strategies or [
            RecencyStrategyExecutor(),
            EngagementVelocityStrategyExecutor(),
            SubstanceProxyStrategyExecutor(),
        ]
        duplicate_strategy_names = {
            strategy.strategy_name
            for strategy in strategy_list
            if sum(
                1
                for item in strategy_list
                if item.strategy_name == strategy.strategy_name
            )
            > 1
        }
        # raises ValueError on duplicate strategy names
        if duplicate_strategy_names:
            raise ValueError(
                "Duplicate strategy executors registered for: "
                + ", ".join(sorted(duplicate_strategy_names))
            )
        self._strategies = {
            strategy.strategy_name: strategy for strategy in strategy_list
        }

    def execute(
        self,
        skill: SkillDocument,
        videos: list[VideoRecord],
    ) -> SkillExecutionResult:
        strategy_name = skill.strategy
        strategy = self._strategies.get(strategy_name or "")
        # raises ValueError if strategy name is unknown
        if strategy is None:
            raise ValueError(
                f"Unsupported skill strategy '{strategy_name}'. Add an adapter or use explicit selected IDs."
            )
        return strategy.execute(videos)
        # reads skill.strategy → looks up executor → calls executor.execute(videos)
