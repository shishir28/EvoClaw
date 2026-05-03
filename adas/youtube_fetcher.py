"""
YouTube data collection with caching.

Usage:
    fetcher = YouTubeFetcher()
    videos = fetcher.fetch(queries=["AI startup 2025"], days=7, max_per_query=10)
    fetcher.save_cache(videos, "test_sets/video_cache_w1.json")
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )

    _TRANSCRIPT_AVAILABLE = True
except ImportError:
    _TRANSCRIPT_AVAILABLE = False

try:
    from config import (
        MAX_RESULTS_PER_QUERY,
        TEST_SETS_DIR,
        TRANSCRIPT_ENABLED,
        VIDEO_WINDOW_DAYS,
        YOUTUBE_API_KEY,
    )
except ModuleNotFoundError:
    from adas.config import (
        MAX_RESULTS_PER_QUERY,
        TEST_SETS_DIR,
        TRANSCRIPT_ENABLED,
        VIDEO_WINDOW_DAYS,
        YOUTUBE_API_KEY,
    )

# ISO 8601 duration → seconds
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


class VideoStub(TypedDict):
    video_id: str
    title: str
    channel: str
    channel_id: str
    published_at: str
    description: str
    thumbnail: str
    query_matched: str


class VideoRecordPayload(VideoStub, total=False):
    views: int
    likes: int
    subscriber_count: int | None
    duration_seconds: int
    tags: list[str]
    category_id: str
    views_per_hour: float
    url: str
    transcript: str | None


def _parse_duration(iso: str) -> int:
    """Convert an ISO 8601 duration string (e.g. 'PT1H30M') to total seconds."""
    m = _DURATION_RE.match(iso or "")
    if not m:
        return 0
    h, min_, s = (int(x or 0) for x in m.groups())
    return h * 3600 + min_ * 60 + s


def _views_per_hour(views: int, published_at: str) -> float:
    """Calculate views per hour since publication, with a 1-hour minimum age floor."""
    pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    age_hours = max((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1)
    return round(views / age_hours, 2)


class YouTubeAPIClient:
    def __init__(self, api_key: str = YOUTUBE_API_KEY) -> None:
        """Build the YouTube API service client and initialise the per-session subscriber cache."""
        if not api_key:
            raise ValueError(
                "YOUTUBE_API_KEY is not set. Export it as an env variable."
            )
        self._yt = build("youtube", "v3", developerKey=api_key)
        self._subscriber_count_cache: dict[str, int | None] = {}

    def _build_video_stub(self, item: dict, query: str) -> VideoStub:
        """Extract the lightweight VideoStub fields from a raw YouTube search result item."""
        snippet = item["snippet"]
        return {
            "video_id": item["id"]["videoId"],
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "channel_id": snippet["channelId"],
            "published_at": snippet["publishedAt"],
            "description": snippet.get("description", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "query_matched": query,
        }

    def _merge_video_details(
        self,
        stub: VideoStub,
        detail: dict,
        channel_subscribers: dict[str, int | None],
    ) -> VideoRecordPayload:
        """Merge statistics and content-detail fields from the videos.list API onto an existing stub."""
        stats = detail.get("statistics", {})
        content = detail.get("contentDetails", {})
        snippet = detail.get("snippet", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        duration_sec = _parse_duration(content.get("duration", ""))

        return {
            **stub,
            "views": views,
            "likes": likes,
            "subscriber_count": channel_subscribers.get(stub["channel_id"]),
            "duration_seconds": duration_sec,
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId", ""),
            "views_per_hour": _views_per_hour(views, stub["published_at"]),
            "url": f"https://www.youtube.com/watch?v={stub['video_id']}",
        }

    def _payload_from_stub(
        self,
        stub: VideoStub,
        channel_subscribers: dict[str, int | None],
    ) -> VideoRecordPayload:
        """Build a zero-stats payload from a stub when the videos.list API returns no detail for a video."""
        return {
            **stub,
            "views": 0,
            "likes": 0,
            "subscriber_count": channel_subscribers.get(stub["channel_id"]),
            "duration_seconds": 0,
            "tags": [],
            "category_id": "",
            "views_per_hour": 0.0,
            "url": f"https://www.youtube.com/watch?v={stub['video_id']}",
            "transcript": None,
        }

    def search(
        self,
        query: str,
        published_after: str,
        max_results: int,
    ) -> list[VideoStub]:
        """Search YouTube for videos matching query published after the given ISO timestamp."""
        try:
            resp = (
                self._yt.search()
                .list(
                    q=query,
                    part="id,snippet",
                    type="video",
                    order="date",
                    publishedAfter=published_after,
                    maxResults=min(max_results, 50),
                    relevanceLanguage="en",
                )
                .execute()
            )
        except HttpError as e:
            print(f"[search] HttpError for '{query}': {e}", file=sys.stderr)
            return []

        results: list[VideoStub] = []
        for item in resp.get("items", []):
            results.append(self._build_video_stub(item, query))
        return results

    def enrich(self, stubs: list[VideoStub]) -> list[VideoRecordPayload]:
        """Fetch statistics, duration, and tags for a list of stubs via the videos.list API in batches of 50."""
        enriched: list[VideoRecordPayload] = []
        channel_subscribers = self.channel_subscriber_counts(stubs)
        for i in range(0, len(stubs), 50):
            batch = stubs[i : i + 50]
            ids = ",".join(v["video_id"] for v in batch)
            try:
                resp = (
                    self._yt.videos()
                    .list(part="statistics,contentDetails,snippet", id=ids)
                    .execute()
                )
            except HttpError as e:
                print(
                    f"[enrich] HttpError for batch, skipping {len(batch)} videos: {e}",
                    file=sys.stderr,
                )
                continue

            detail_map = {item["id"]: item for item in resp.get("items", [])}
            for stub in batch:
                detail = detail_map.get(stub["video_id"])
                if not detail:
                    print(
                        f"[enrich] skipping {stub['video_id']}: no detail returned by API",
                        file=sys.stderr,
                    )
                    continue

                enriched.append(
                    self._merge_video_details(stub, detail, channel_subscribers)
                )
        return enriched

    def channel_subscriber_counts(
        self,
        videos: list[VideoStub],
    ) -> dict[str, int | None]:
        """Return subscriber counts keyed by channel ID, using an in-session cache to avoid redundant API calls."""
        channel_ids = sorted({video["channel_id"] for video in videos})
        if not channel_ids:
            return {}

        missing_channel_ids = [
            channel_id
            for channel_id in channel_ids
            if channel_id not in self._subscriber_count_cache
        ]
        for i in range(0, len(missing_channel_ids), 50):
            batch = missing_channel_ids[i : i + 50]
            try:
                resp = (
                    self._yt.channels()
                    .list(part="statistics", id=",".join(batch))
                    .execute()
                )
            except HttpError as e:
                print(f"[channels] HttpError: {e}", file=sys.stderr)
                for channel_id in batch:
                    self._subscriber_count_cache[channel_id] = None
                continue

            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                subs_raw = stats.get("subscriberCount")
                self._subscriber_count_cache[item["id"]] = (
                    int(subs_raw) if subs_raw is not None else None
                )

            for channel_id in batch:
                self._subscriber_count_cache.setdefault(channel_id, None)

        return {
            channel_id: self._subscriber_count_cache.get(channel_id)
            for channel_id in channel_ids
        }


class TranscriptProvider:
    def __init__(self, pacing_seconds: float = 0.2) -> None:
        """Initialise the transcript API client and configure inter-request pacing delay."""
        self._transcript_api = YouTubeTranscriptApi() if _TRANSCRIPT_AVAILABLE else None
        self._pacing_seconds = pacing_seconds

    @property
    def available(self) -> bool:
        """Return True if the youtube-transcript-api package is installed and the client is ready."""
        return self._transcript_api is not None

    def attach(self, videos: list[VideoRecordPayload]) -> list[VideoRecordPayload]:
        """Fetch and attach English transcripts to each video in-place, capped at 3000 characters."""
        if not self.available:
            return videos

        for video in videos:
            vid_id = video["video_id"]
            try:
                fetched = self._transcript_api.fetch(vid_id, languages=["en", "en-US"])
                segments = (
                    fetched.to_raw_data()
                    if hasattr(fetched, "to_raw_data")
                    else fetched
                )
                text = " ".join(
                    seg["text"] if isinstance(seg, dict) else seg.text
                    for seg in segments
                )
                # Cap at ~3000 chars so prompts stay manageable
                video["transcript"] = text[:3000]
            except (TranscriptsDisabled, NoTranscriptFound):
                video["transcript"] = None
            except Exception as e:
                print(f"[transcript] {vid_id}: {e}", file=sys.stderr)
                video["transcript"] = None
            time.sleep(self._pacing_seconds)
        return videos


class VideoCacheRepository:
    def _resolve_path(self, path: str) -> Path:
        """Return an absolute Path, prefixing with TEST_SETS_DIR when a relative path is given."""
        return Path(path) if os.path.isabs(path) else Path(TEST_SETS_DIR) / path

    def save(self, videos: list[VideoRecordPayload], path: str) -> None:
        """Serialise the video list to a JSON file with a fetch timestamp and count envelope."""
        dest = self._resolve_path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(videos),
            "videos": videos,
        }
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"Cached {len(videos)} videos → {dest}")

    def load(self, path: str) -> list[VideoRecordPayload]:
        """Read a previously saved cache file and return its video list."""
        dest = self._resolve_path(path)
        raw = json.loads(dest.read_text())
        return raw["videos"]


class YouTubeFetcher:
    def __init__(
        self,
        api_key: str = YOUTUBE_API_KEY,
        api_client: YouTubeAPIClient | None = None,
        transcript_provider: TranscriptProvider | None = None,
        cache_repository: VideoCacheRepository | None = None,
    ) -> None:
        """Wire up the API client, transcript provider, and cache repository, creating defaults when not injected."""
        self._api_client = api_client or YouTubeAPIClient(api_key)
        self._transcript_provider = transcript_provider or TranscriptProvider()
        self._cache_repository = cache_repository or VideoCacheRepository()

    def fetch(
        self,
        queries: list[str],
        days: int = VIDEO_WINDOW_DAYS,
        max_per_query: int = MAX_RESULTS_PER_QUERY,
        with_transcripts: bool = TRANSCRIPT_ENABLED,
    ) -> list[VideoRecordPayload]:
        """Return deduplicated, enriched video records for all queries."""
        published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        seen: dict[str, VideoStub] = {}
        for query in queries:
            for video in self._api_client.search(query, published_after, max_per_query):
                if video["video_id"] not in seen:
                    seen[video["video_id"]] = video

        if not seen:
            return []

        enriched = self._api_client.enrich(list(seen.values()))
        if with_transcripts and self._transcript_provider.available:
            return self._transcript_provider.attach(enriched)
        return enriched

    def save_cache(self, videos: list[VideoRecordPayload], path: str) -> None:
        """Persist the given video list to disk via the injected cache repository."""
        self._cache_repository.save(videos, path)

    @staticmethod
    def load_cache(path: str) -> list[VideoRecordPayload]:
        """Load a cached video list from disk without requiring a fetcher instance."""
        return VideoCacheRepository().load(path)


# ------------------------------------------------------------------
# CLI entry point for manual cache refresh
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    try:
        from config import SEARCH_QUERIES, VIDEO_WINDOW_DAYS
    except ModuleNotFoundError:
        from adas.config import SEARCH_QUERIES, VIDEO_WINDOW_DAYS

    parser = argparse.ArgumentParser(description="Fetch and cache YouTube videos")
    parser.add_argument("--days", type=int, default=VIDEO_WINDOW_DAYS)
    parser.add_argument("--max-per-query", type=int, default=MAX_RESULTS_PER_QUERY)
    parser.add_argument("--output", default="video_cache_w1.json")
    parser.add_argument("--no-transcripts", action="store_true")
    args = parser.parse_args()

    fetcher = YouTubeFetcher()
    videos = fetcher.fetch(
        queries=SEARCH_QUERIES,
        days=args.days,
        max_per_query=args.max_per_query,
        with_transcripts=not args.no_transcripts,
    )
    print(f"Fetched {len(videos)} unique videos")
    fetcher.save_cache(videos, args.output)
