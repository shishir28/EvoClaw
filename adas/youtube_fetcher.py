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
from datetime import datetime, timezone, timedelta
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    _TRANSCRIPT_AVAILABLE = True
except ImportError:
    _TRANSCRIPT_AVAILABLE = False

from config import (
    YOUTUBE_API_KEY,
    MAX_RESULTS_PER_QUERY,
    VIDEO_WINDOW_DAYS,
    TRANSCRIPT_ENABLED,
    TEST_SETS_DIR,
)

# ISO 8601 duration → seconds
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_duration(iso: str) -> int:
    m = _DURATION_RE.match(iso or "")
    if not m:
        return 0
    h, min_, s = (int(x or 0) for x in m.groups())
    return h * 3600 + min_ * 60 + s


def _views_per_hour(views: int, published_at: str) -> float:
    pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    age_hours = max((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1)
    return round(views / age_hours, 2)


class YouTubeFetcher:
    def __init__(self, api_key: str = YOUTUBE_API_KEY):
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is not set. Export it as an env variable.")
        self._yt = build("youtube", "v3", developerKey=api_key)
        self._transcript_api = YouTubeTranscriptApi() if _TRANSCRIPT_AVAILABLE else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        queries: list[str],
        days: int = VIDEO_WINDOW_DAYS,
        max_per_query: int = MAX_RESULTS_PER_QUERY,
        with_transcripts: bool = TRANSCRIPT_ENABLED,
    ) -> list[dict]:
        """Return deduplicated, enriched video records for all queries."""
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        seen: dict[str, dict] = {}
        for query in queries:
            for video in self._search(query, published_after, max_per_query):
                if video["video_id"] not in seen:
                    seen[video["video_id"]] = video

        if not seen:
            return []

        enriched = self._enrich(list(seen.values()))

        if with_transcripts and _TRANSCRIPT_AVAILABLE:
            enriched = self._attach_transcripts(enriched)

        return enriched

    def save_cache(self, videos: list[dict], path: str) -> None:
        """Write enriched video list to a JSON cache file."""
        dest = Path(path) if os.path.isabs(path) else Path(TEST_SETS_DIR) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(videos),
            "videos": videos,
        }
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"Cached {len(videos)} videos → {dest}")

    @staticmethod
    def load_cache(path: str) -> list[dict]:
        """Load a previously saved cache file."""
        dest = Path(path) if os.path.isabs(path) else Path(TEST_SETS_DIR) / path
        raw = json.loads(dest.read_text())
        return raw["videos"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self, query: str, published_after: str, max_results: int) -> list[dict]:
        """Run a YouTube search and return stub records with video IDs."""
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

        results = []
        for item in resp.get("items", []):
            snippet = item["snippet"]
            results.append({
                "video_id": item["id"]["videoId"],
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "channel_id": snippet["channelId"],
                "published_at": snippet["publishedAt"],
                "description": snippet.get("description", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "query_matched": query,
            })
        return results

    def _enrich(self, stubs: list[dict]) -> list[dict]:
        """Fetch per-video statistics and content details in batches of 50."""
        enriched = []
        for i in range(0, len(stubs), 50):
            batch = stubs[i : i + 50]
            ids = ",".join(v["video_id"] for v in batch)
            channel_subscribers = self._channel_subscriber_counts(batch)
            try:
                resp = (
                    self._yt.videos()
                    .list(part="statistics,contentDetails,snippet", id=ids)
                    .execute()
                )
            except HttpError as e:
                print(f"[enrich] HttpError: {e}", file=sys.stderr)
                enriched.extend(batch)
                continue

            detail_map = {item["id"]: item for item in resp.get("items", [])}
            for stub in batch:
                detail = detail_map.get(stub["video_id"])
                if not detail:
                    enriched.append(stub)
                    continue

                stats = detail.get("statistics", {})
                content = detail.get("contentDetails", {})
                snippet = detail.get("snippet", {})

                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                duration_sec = _parse_duration(content.get("duration", ""))

                enriched.append({
                    **stub,
                    "views": views,
                    "likes": likes,
                    "subscriber_count": channel_subscribers.get(stub["channel_id"]),
                    "duration_seconds": duration_sec,
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId", ""),
                    "views_per_hour": _views_per_hour(views, stub["published_at"]),
                    "url": f"https://www.youtube.com/watch?v={stub['video_id']}",
                })
        return enriched

    def _channel_subscriber_counts(self, videos: list[dict]) -> dict[str, int | None]:
        """Return subscriber counts keyed by channel ID for a batch of videos."""
        channel_ids = sorted({video["channel_id"] for video in videos})
        if not channel_ids:
            return {}

        subscribers: dict[str, int | None] = {}
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i : i + 50]
            try:
                resp = (
                    self._yt.channels()
                    .list(part="statistics", id=",".join(batch))
                    .execute()
                )
            except HttpError as e:
                print(f"[channels] HttpError: {e}", file=sys.stderr)
                for channel_id in batch:
                    subscribers[channel_id] = None
                continue

            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                subs_raw = stats.get("subscriberCount")
                subscribers[item["id"]] = int(subs_raw) if subs_raw is not None else None

            for channel_id in batch:
                subscribers.setdefault(channel_id, None)

        return subscribers

    def _attach_transcripts(self, videos: list[dict]) -> list[dict]:
        """Best-effort transcript fetch; skips on errors."""
        for video in videos:
            vid_id = video["video_id"]
            try:
                fetched = self._transcript_api.fetch(vid_id, languages=["en", "en-US"])
                segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
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
            time.sleep(0.2)   # gentle pacing
        return videos


# ------------------------------------------------------------------
# CLI entry point for manual cache refresh
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from config import SEARCH_QUERIES, VIDEO_WINDOW_DAYS

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
