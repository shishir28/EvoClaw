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
    from .models import SkillDocument, VideoRecord
except ImportError:
    from evaluation.models import SkillDocument, VideoRecord


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
    ("\u0b80", "\u0bff"),
    ("\u0c00", "\u0c7f"),
    ("\u0c80", "\u0cff"),
    ("\u0d00", "\u0d7f"),
    ("\u4e00", "\u9fff"),
]

_ALLOWED_LANGUAGE_PREFIXES = ("en",)

_NON_ENGLISH_LANGUAGE_CODES = {
    "hi",
    "kn",
    "ml",
    "ta",
    "te",
    "ur",
    "vi",
    "zh",
}

_NON_ENGLISH_LATIN_MARKERS = {
    "hindi",
    "hinglish",
    "kannada",
    "malayalam",
    "tamil",
    "telangana",
    "telugu",
    "singam",
    "erangiruchu",
}

_HINDI_LATIN_PARTICLES = {
    "ne",
    "ko",
    "mein",
    "maine",
    "kiye",
    "sabse",
}


def _text(video: VideoRecord) -> str:
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


def _language_code_is_english(code: str) -> bool:
    normalized = (code or "").lower()
    return not normalized or normalized.startswith(_ALLOWED_LANGUAGE_PREFIXES)


def _has_non_english_language_code(video: VideoRecord) -> bool:
    codes = [
        getattr(video, "default_language", ""),
        getattr(video, "default_audio_language", ""),
    ]
    normalized_codes = [code.lower() for code in codes if code]
    return any(
        code.split("-")[0] in _NON_ENGLISH_LANGUAGE_CODES
        or not _language_code_is_english(code)
        for code in normalized_codes
    )


def _has_non_english_latin_markers(video: VideoRecord) -> bool:
    words = set(re.findall(r"[a-z]+", _text(video)))
    if words & _NON_ENGLISH_LATIN_MARKERS:
        return True
    return len(words & _HINDI_LATIN_PARTICLES) >= 2


def _looks_english(video: VideoRecord) -> bool:
    # Reject explicit non-English language metadata, blocked scripts, and common Latin-script language markers.
    source = " ".join([video.title, video.description])
    if _has_non_english_language_code(video):
        return False
    if _contains_blocked_script(source):
        return False
    if _has_non_english_latin_markers(video):
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


MIN_PREFERRED_DURATION_MINUTES = 5.0


def _preferred_duration_pool(
    candidates: list[VideoRecord],
    minimum_minutes: float = MIN_PREFERRED_DURATION_MINUTES,
) -> list[VideoRecord]:
    return [video for video in candidates if _minutes(video) >= minimum_minutes]


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
        return [
            video for video in videos if _looks_english(video) and _is_relevant(video)
        ]


class RecencyStrategyExecutor(_BaseStrategyExecutor):
    strategy_name = "recency"

    def execute(self, videos: list[VideoRecord]) -> SkillExecutionResult:
        candidates = [
            video
            for video in self.base_candidates(videos)
            if _subscriber_floor(video, 1000)
        ]
        # Prefer the 48h window, but fall back to the full candidate pool when it is too sparse.
        recent_candidates = [video for video in candidates if _age_hours(video) <= 48.0]
        pool = recent_candidates if len(recent_candidates) >= 3 else candidates

        preferred = sorted(
            _preferred_duration_pool(pool),
            key=_published_at,
            reverse=True,
        )
        fallback = sorted(
            [video for video in pool if video not in preferred],
            key=_published_at,
            reverse=True,
        )
        selected = (preferred + fallback)[:3]
        duration_note = (
            f"Preferred {min(len(preferred), 3)} video(s) at least "
            f"{MIN_PREFERRED_DURATION_MINUTES:g} minutes long."
        )
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in selected],
            notes=[
                "Executed recency strategy adapter.",
                duration_note,
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
        # Prefer larger channels, but relax the subscriber floor when the pool is too sparse.
        pool = primary_pool
        if len(pool) < 3:
            pool = [video for video in candidates if _subscriber_floor(video, 1000)]
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
        # Approximate substance without an LLM: richer text and reasonable duration rank higher.
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
        if strategy is None:
            raise ValueError(
                f"Unsupported skill strategy '{strategy_name}'. Add an adapter or use explicit selected IDs."
            )
        return strategy.execute(videos)
