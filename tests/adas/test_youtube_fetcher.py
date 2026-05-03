"""
Tests for adas/youtube_fetcher.py
"""

from __future__ import annotations

from youtube_fetcher import TranscriptProvider


class TestTranscriptProvider:
    def test_returns_videos_unchanged_when_transcript_client_is_unavailable(self):
        provider = TranscriptProvider.__new__(TranscriptProvider)
        provider._transcript_api = None
        provider._pacing_seconds = 0.0

        videos = [
            {
                "video_id": "abc123",
                "title": "Example",
                "channel": "Channel",
                "channel_id": "chan-1",
                "published_at": "2026-05-01T00:00:00Z",
                "description": "Example description",
                "thumbnail": "",
                "query_matched": "ai startup",
                "views": 0,
                "likes": 0,
                "subscriber_count": None,
                "duration_seconds": 0,
                "tags": [],
                "category_id": "",
                "views_per_hour": 0.0,
                "url": "https://www.youtube.com/watch?v=abc123",
                "transcript": None,
            }
        ]

        result = provider.attach(videos)

        assert result is videos
        assert result[0]["transcript"] is None
