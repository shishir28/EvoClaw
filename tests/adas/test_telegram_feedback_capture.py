"""Tests for ReactionFeedbackCapture and _emoji_to_reaction."""

from __future__ import annotations

import json

import pytest

from adas.telegram.feedback_capture import ReactionFeedbackCapture, _emoji_to_reaction
from adas.telegram.models import DeliveryRecord, TelegramDigestPick
from adas.telegram.reaction_poller import ReactionUpdate


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _make_delivery_record(
    message_id: int = 10,
    selected_video_ids: list[str] | None = None,
    cache_path: str = "/fake/cache.json",
    dry_run: bool = False,
    skill_version: str | None = "skill_003",
) -> DeliveryRecord:
    return DeliveryRecord(
        delivered_at="2026-05-17T07:00:00+00:00",
        dry_run=dry_run,
        skill_name="recency-first",
        skill_version=skill_version,
        strategy="recency",
        production_skill_path="/fake/SKILL.md",
        cache_path=cache_path,
        feedback_path=None,
        telegram_chat_id="chat-1",
        telegram_message_id=message_id,
        selected_video_ids=selected_video_ids or ["v1", "v2", "v3"],
    )


def _reaction_update(
    update_id: int = 1001,
    message_id: int = 10,
    new_reactions: list[str] | None = None,
) -> ReactionUpdate:
    return ReactionUpdate(
        update_id=update_id,
        message_id=message_id,
        chat_id="chat-1",
        new_reactions=new_reactions or ["👍"],
        old_reactions=[],
        date=1700000000,
    )


class _StubPoller:
    def __init__(self, updates: list[ReactionUpdate]):
        self._updates = updates
        self.polled_offsets: list[int | None] = []

    def poll(self, offset: int | None = None, limit: int = 100) -> list[ReactionUpdate]:
        self.polled_offsets.append(offset)
        return self._updates


class _StubDeliveryLogStore:
    def __init__(self, records: list[DeliveryRecord]):
        self._records = records

    def load_history(self) -> list[DeliveryRecord]:
        return self._records


class _StubFeedbackService:
    def __init__(self):
        self.calls: list[dict] = []

    def append_feedback(self, date, picks, available_videos, skill_version=None, feedback_path=None):
        self.calls.append({
            "date": date,
            "picks": picks,
            "available_videos": available_videos,
            "skill_version": skill_version,
            "feedback_path": feedback_path,
        })


class _StubCacheRepository:
    def __init__(self, videos: list[dict]):
        self._videos = videos

    def load(self, path: str) -> list[dict]:
        return self._videos


def _raw_video(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "title": f"Video {video_id}",
        "channel": "TestChannel",
        "channel_id": "ch1",
        "published_at": "2026-05-10T00:00:00Z",
        "description": "desc",
        "thumbnail": "",
        "query_matched": "AI startup",
        "views": 1000,
        "likes": 50,
        "subscriber_count": None,
        "duration_seconds": 600,
        "tags": [],
        "category_id": "28",
        "views_per_hour": 10.0,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript": None,
    }


def _make_cache_file(tmp_path: Path, video_ids: list[str] | None = None) -> Path:
    """Write a minimal cache JSON to a temp file and return its path."""
    ids = video_ids or ["v1", "v2", "v3"]
    cache = {
        "fetched_at": "2026-05-17T00:00:00Z",
        "count": len(ids),
        "videos": [_raw_video(vid) for vid in ids],
    }
    p = tmp_path / "cache.json"
    p.write_text(json.dumps(cache))
    return p


def _capture(
    updates: list[ReactionUpdate],
    records: list[DeliveryRecord] | None = None,
    videos: list[dict] | None = None,
) -> tuple[ReactionFeedbackCapture, _StubFeedbackService]:
    fb = _StubFeedbackService()
    capture = ReactionFeedbackCapture(
        poller=_StubPoller(updates),
        delivery_log_store=_StubDeliveryLogStore(records or []),
        feedback_service=fb,
        cache_repository=_StubCacheRepository(videos or [_raw_video("v1"), _raw_video("v2"), _raw_video("v3")]),
    )
    return capture, fb


# ---------------------------------------------------------------------------
# _emoji_to_reaction
# ---------------------------------------------------------------------------

class TestEmojiToReaction:
    @pytest.mark.parametrize("emoji", ["👍", "❤", "🔥", "⭐", "🎉"])
    def test_positive_emojis_map_to_thumbs_up(self, emoji):
        assert _emoji_to_reaction(emoji) == "👍"

    @pytest.mark.parametrize("emoji", ["👎", "💔", "🤮"])
    def test_negative_emojis_map_to_thumbs_down(self, emoji):
        assert _emoji_to_reaction(emoji) == "👎"

    def test_unknown_emoji_returns_none(self):
        assert _emoji_to_reaction("😂") is None

    def test_empty_string_returns_none(self):
        assert _emoji_to_reaction("") is None


# ---------------------------------------------------------------------------
# No updates
# ---------------------------------------------------------------------------

class TestCaptureNoUpdates:
    def test_returns_zero_counts_when_no_updates(self, tmp_path):
        capture, fb = _capture(updates=[])
        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.updates_processed == 0
        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 0
        assert len(fb.calls) == 0

    def test_preserves_existing_offset_when_no_updates(self, tmp_path):
        offset_file = tmp_path / "offset.json"
        offset_file.write_text('{"offset": 42}')
        capture, _ = _capture(updates=[])

        result = capture.capture(offset_path=str(offset_file))

        assert result.new_offset == 42


# ---------------------------------------------------------------------------
# Matching reactions
# ---------------------------------------------------------------------------

class TestCaptureMatchingReaction:
    def test_writes_feedback_entry_for_matching_message_id(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1", "v2", "v3"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1", "v2", "v3"],
                                       cache_path=str(cache))
        update = _reaction_update(message_id=10, new_reactions=["👍"])
        capture, fb = _capture([update], records=[record])

        result = capture.capture(
            offset_path=str(tmp_path / "offset.json"),
            feedback_path=str(tmp_path / "feedback.json"),
        )

        assert result.feedback_entries_written == 1
        assert result.skipped_no_match == 0
        assert len(fb.calls) == 1
        assert fb.calls[0]["skill_version"] == "skill_003"

    def test_maps_thumbs_up_emoji_to_up_reaction_for_all_picks(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1", "v2"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1", "v2"],
                                       cache_path=str(cache))
        update = _reaction_update(message_id=10, new_reactions=["👍"])
        capture, fb = _capture([update], records=[record],
                                videos=[_raw_video("v1"), _raw_video("v2")])

        capture.capture(offset_path=str(tmp_path / "offset.json"))

        picks = fb.calls[0]["picks"]
        assert len(picks) == 2
        assert all(p.reaction == "👍" for p in picks)

    def test_maps_thumbs_down_emoji_to_down_reaction(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1"],
                                       cache_path=str(cache))
        update = _reaction_update(message_id=10, new_reactions=["👎"])
        capture, fb = _capture([update], records=[record], videos=[_raw_video("v1")])

        capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert fb.calls[0]["picks"][0].reaction == "👎"

    def test_uses_first_recognised_reaction_when_multiple_present(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1"],
                                       cache_path=str(cache))
        update = _reaction_update(message_id=10, new_reactions=["🔥", "👎"])
        capture, fb = _capture([update], records=[record], videos=[_raw_video("v1")])

        capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert fb.calls[0]["picks"][0].reaction == "👍"  # 🔥 maps to 👍

    def test_result_message_describes_written_entry(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1", "v2", "v3"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1", "v2", "v3"],
                                       cache_path=str(cache))
        update = _reaction_update(message_id=10, new_reactions=["👍"])
        capture, _ = _capture([update], records=[record])

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert len(result.messages) == 1
        assert "message_id=10" in result.messages[0]
        assert "3 picks" in result.messages[0]


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

class TestCaptureSkips:
    def test_skips_update_with_no_matching_delivery_record(self, tmp_path):
        update = _reaction_update(message_id=999, new_reactions=["👍"])
        capture, fb = _capture([update], records=[])

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 1
        assert len(fb.calls) == 0

    def test_skips_unrecognised_emoji(self, tmp_path):
        record = _make_delivery_record(message_id=10)
        update = _reaction_update(message_id=10, new_reactions=["😂"])
        capture, fb = _capture([update], records=[record])

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 1

    def test_skips_empty_new_reactions(self, tmp_path):
        record = _make_delivery_record(message_id=10)
        update = _reaction_update(message_id=10, new_reactions=[])
        capture, fb = _capture([update], records=[record])

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 1

    def test_excludes_dry_run_delivery_records_from_delivery_map(self, tmp_path):
        record = _make_delivery_record(message_id=10, dry_run=True)
        update = _reaction_update(message_id=10, new_reactions=["👍"])
        capture, fb = _capture([update], records=[record])

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 1

    def test_skips_when_cache_file_missing(self, tmp_path):
        record = _make_delivery_record(message_id=10, cache_path="/nonexistent/cache.json")
        update = _reaction_update(message_id=10, new_reactions=["👍"])

        class _EmptyCache:
            def load(self, path):
                raise FileNotFoundError(path)

        capture = ReactionFeedbackCapture(
            poller=_StubPoller([update]),
            delivery_log_store=_StubDeliveryLogStore([record]),
            feedback_service=_StubFeedbackService(),
            cache_repository=_EmptyCache(),
        )

        result = capture.capture(offset_path=str(tmp_path / "offset.json"))

        assert result.feedback_entries_written == 0
        assert result.skipped_no_match == 1


# ---------------------------------------------------------------------------
# Offset persistence
# ---------------------------------------------------------------------------

class TestOffsetPersistence:
    def test_saves_offset_as_last_update_id_plus_one(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1"],
                                       cache_path=str(cache))
        update = _reaction_update(update_id=500, message_id=10, new_reactions=["👍"])
        capture, _ = _capture([update], records=[record])
        offset_file = tmp_path / "offset.json"

        result = capture.capture(offset_path=str(offset_file))

        assert result.new_offset == 501
        assert json.loads(offset_file.read_text())["offset"] == 501

    def test_loads_existing_offset_and_passes_to_poller(self, tmp_path):
        offset_file = tmp_path / "offset.json"
        offset_file.write_text('{"offset": 200}')
        poller = _StubPoller([])
        capture = ReactionFeedbackCapture(
            poller=poller,
            delivery_log_store=_StubDeliveryLogStore([]),
            feedback_service=_StubFeedbackService(),
            cache_repository=_StubCacheRepository([]),
        )

        capture.capture(offset_path=str(offset_file))

        assert poller.polled_offsets[0] == 200

    def test_passes_none_offset_when_no_offset_file(self, tmp_path):
        poller = _StubPoller([])
        capture = ReactionFeedbackCapture(
            poller=poller,
            delivery_log_store=_StubDeliveryLogStore([]),
            feedback_service=_StubFeedbackService(),
            cache_repository=_StubCacheRepository([]),
        )

        capture.capture(offset_path=str(tmp_path / "nonexistent_offset.json"))

        assert poller.polled_offsets[0] is None

    def test_multiple_updates_advances_offset_to_last(self, tmp_path):
        cache = _make_cache_file(tmp_path, ["v1"])
        record = _make_delivery_record(message_id=10, selected_video_ids=["v1"],
                                       cache_path=str(cache))
        updates = [
            _reaction_update(update_id=100, message_id=10, new_reactions=["👍"]),
            _reaction_update(update_id=101, message_id=999, new_reactions=["👎"]),
        ]
        capture, _ = _capture(updates, records=[record])
        offset_file = tmp_path / "offset.json"

        result = capture.capture(offset_path=str(offset_file))

        assert result.new_offset == 102
