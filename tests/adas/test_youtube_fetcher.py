"""
Tests for adas/youtube_fetcher.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import adas.youtube_fetcher as youtube_fetcher
from adas.youtube_fetcher import TranscriptProvider, VideoCacheRepository


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

    def test_builds_generic_proxy_config_from_urls(self, monkeypatch):
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_WEBSHARE_USERNAME", "")
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_WEBSHARE_PASSWORD", "")
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_PROXY_HTTP_URL", "http://proxy.local:8080")
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_PROXY_HTTPS_URL", "https://proxy.local:8443")

        proxy_config = youtube_fetcher._build_transcript_proxy_config()

        assert proxy_config.to_requests_dict() == {
            "http": "http://proxy.local:8080",
            "https": "https://proxy.local:8443",
        }

    def test_builds_webshare_proxy_config_when_credentials_are_set(self, monkeypatch):
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_WEBSHARE_USERNAME", "user")
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_WEBSHARE_PASSWORD", "pass")
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_WEBSHARE_LOCATIONS", ("AU",))
        monkeypatch.setattr(youtube_fetcher, "TRANSCRIPT_PROXY_RETRIES_WHEN_BLOCKED", 3)

        proxy_config = youtube_fetcher._build_transcript_proxy_config()

        assert proxy_config.retries_when_blocked == 3
        assert proxy_config.to_requests_dict()["https"].startswith("http://user-AU-rotate:pass@")


def _write_cache(path, fetched_at: str, count: int = 2) -> None:
    path.write_text(
        json.dumps(
            {
                "fetched_at": fetched_at,
                "count": count,
                "videos": [{"video_id": f"v{i}"} for i in range(count)],
            }
        )
    )


class TestVideoCacheMetadata:
    def test_load_metadata_computes_age_from_fetched_at(self, tmp_path):
        cache = tmp_path / "cache.json"
        _write_cache(cache, "2026-05-22T00:00:00+00:00", count=3)

        meta = VideoCacheRepository().load_metadata(
            str(cache), now=datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc)
        )

        assert meta.exists is True
        assert meta.count == 3
        assert meta.age_hours == 24.0
        assert meta.fetched_at == datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc)

    def test_load_metadata_missing_file_is_not_an_error(self, tmp_path):
        meta = VideoCacheRepository().load_metadata(str(tmp_path / "absent.json"))

        assert meta.exists is False
        assert meta.age_hours is None
        assert meta.count == 0

    def test_load_metadata_handles_missing_timestamp(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"count": 1, "videos": [{"video_id": "v0"}]}))

        meta = VideoCacheRepository().load_metadata(str(cache))

        assert meta.exists is True
        assert meta.fetched_at is None
        assert meta.age_hours is None
        assert meta.count == 1

    def test_count_returns_zero_when_cache_absent(self, tmp_path):
        assert VideoCacheRepository().count(str(tmp_path / "absent.json")) == 0

    def test_count_returns_zero_for_corrupt_cache(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("{not json")

        assert VideoCacheRepository().count(str(cache)) == 0
