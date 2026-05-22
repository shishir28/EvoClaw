"""Format selected videos into a Telegram-friendly digest message."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

try:
    from ..evaluation.models import VideoRecord
    from .models import TelegramDigestPick
except ImportError:
    from evaluation.models import VideoRecord
    from telegram.models import TelegramDigestPick


_URL_PATTERN = re.compile(r"https?://\S+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def _published_at(video: VideoRecord) -> datetime:
    return datetime.fromisoformat(video.published_at.replace("Z", "+00:00"))


def _duration_minutes(video: VideoRecord) -> int:
    minutes = round(float(video.duration_seconds or 0) / 60.0)
    return max(minutes, 1)


def _age_label(video: VideoRecord, now: datetime) -> str:
    age_seconds = max((now - _published_at(video)).total_seconds(), 0.0)
    age_hours = age_seconds / 3600.0
    if age_hours < 1.0:
        return "less than 1 hour ago"
    if age_hours < 24.0:
        whole_hours = int(round(age_hours))
        unit = "hour" if whole_hours == 1 else "hours"
        return f"{whole_hours} {unit} ago"
    age_days = int(round(age_hours / 24.0))
    unit = "day" if age_days == 1 else "days"
    return f"{age_days} {unit} ago"


def _clean_summary_text(text: str) -> str:
    without_urls = _URL_PATTERN.sub("", text)
    return _WHITESPACE_PATTERN.sub(" ", without_urls).strip(" -\n\t")


def _fallback_summary(video: VideoRecord) -> str:
    topic = video.query_matched or "AI + startup work"
    if video.views_per_hour > 0:
        return (
            f"Useful for staying current on {topic.lower()}, with roughly "
            f"{int(round(video.views_per_hour)):,} views per hour right now."
        )
    return f"Useful for staying current on {topic.lower()} from a founder-oriented channel."


def _why_watch(video: VideoRecord) -> str:
    source = _clean_summary_text(video.transcript_or_description)
    if source:
        for sentence in _SENTENCE_SPLIT_PATTERN.split(source):
            cleaned = _clean_summary_text(sentence)
            if len(cleaned) < 40:
                continue
            if cleaned.casefold() == video.title.strip().casefold():
                continue
            return cleaned[:220].rstrip(" .,;:") + "."
    return _fallback_summary(video)


@dataclass(slots=True)
class TelegramDigestFormatter:
    """Build structured picks plus final message text for Telegram delivery."""

    now_factory: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if self.now_factory is None:
            self.now_factory = lambda: datetime.now(timezone.utc)

    def build_picks(self, videos: list[VideoRecord]) -> list[TelegramDigestPick]:
        now = self.now_factory()
        return [
            TelegramDigestPick(
                rank=index,
                video_id=video.video_id,
                title=video.title,
                channel=video.channel,
                url=video.url,
                duration_minutes=_duration_minutes(video),
                age_label=_age_label(video, now),
                why_watch=_why_watch(video),
            )
            for index, video in enumerate(videos, start=1)
        ]

    def format_pick_message(self, pick: TelegramDigestPick) -> str:
        """Format one recommendation so Telegram reactions map to one video."""
        return "\n".join(
            [
                f'🎬 Pick {pick.rank}: "{pick.title}"',
                f"@{pick.channel} · {pick.duration_minutes} min · {pick.age_label}",
                f"🔗 {pick.url}",
                f"-> {pick.why_watch}",
                "",
                "React 👍 or 👎 to this pick to help me improve future recommendations.",
            ]
        )

    def format_digest(self, picks: list[TelegramDigestPick]) -> str:
        if len(picks) != 3:
            raise ValueError(f"Telegram digests require exactly 3 picks, got {len(picks)}.")

        blocks = [self.format_pick_message(pick) for pick in picks]
        return "\n\n---\n\n".join(blocks)
