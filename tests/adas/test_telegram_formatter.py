"""Tests for Telegram digest formatting."""

from __future__ import annotations

from datetime import datetime, timezone

from adas.telegram.formatter import TelegramDigestFormatter
from builders import video


def test_build_picks_and_format_digest():
    formatter = TelegramDigestFormatter(
        now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
    )
    videos = [
        video()
        .with_id(f"v{i}")
        .with_title(f"Video {i}")
        .with_channel(f"Channel {i}", f"ch{i}")
        .with_age_hours(2 + i)
        .with_duration_seconds(600 + (i * 60))
        .with_description(
            "This breakdown covers real GTM lessons for AI founders and the tradeoffs "
            "behind shipping faster with smaller teams."
        )
        .build()
        for i in range(1, 4)
    ]

    picks = formatter.build_picks(videos)
    message = formatter.format_digest(picks)

    assert len(picks) == 3
    assert picks[0].rank == 1
    assert picks[0].age_label.endswith("ago")
    assert picks[0].duration_minutes == 11
    assert "GTM lessons for AI founders" in picks[0].why_watch
    assert '🎬 Pick 1: "Video 1"' in message
    assert "🔗 https://www.youtube.com/watch?v=v1" in message
    assert "React 👍 or 👎 to this pick to help me improve future recommendations." in message
    assert message.count("React 👍 or 👎 to this pick") == 3


def test_uses_fallback_summary_when_description_is_missing():
    formatter = TelegramDigestFormatter(
        now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
    )
    picks = formatter.build_picks(
        [
            video()
            .with_id(f"v{i}")
            .with_title(f"Video {i}")
            .with_channel(f"Channel {i}", f"ch{i}")
            .with_description("")
            .with_query_matched("AI startup 2026")
            .build()
            for i in range(1, 4)
        ]
    )

    assert picks[0].why_watch.startswith("Useful for staying current on ai startup 2026")
