"""Tests for production digest delivery orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from adas.telegram.delivery_log import DeliveryLogStore
from adas.telegram.formatter import TelegramDigestFormatter
from adas.telegram.models import DeliveryRecord, TelegramSendReceipt
from adas.telegram.service import (
    CacheFreshnessGate,
    ProductionDigestService,
    StaleCacheError,
)
from adas.youtube_fetcher import VideoCacheRepository
from builders import make_request, skill, video


class _StubEvaluator:
    def __init__(self, request, selected_video_ids: list[str]):
        self._request = request
        self._selected_video_ids = selected_video_ids

    def load_request(self, skill_path: str, cache_path: str, feedback_path: str | None = None):
        self._request.cache_path = cache_path
        self._request.feedback_path = feedback_path
        return self._request

    def select_video_ids(self, request, selected_video_ids=None):
        return self._selected_video_ids, ["Executed production strategy."]

    def resolve_selected_videos(self, request, selected_video_ids: list[str]):
        videos_by_id = {video.video_id: video for video in request.videos}
        return [videos_by_id[video_id] for video_id in selected_video_ids]


class _FirstThreeEvaluator(_StubEvaluator):
    def __init__(self, request):
        super().__init__(request, [])

    def select_video_ids(self, request, selected_video_ids=None):
        return [video.video_id for video in request.videos[:3]], ["Executed production strategy."]


class _StubSender:
    chat_id = "chat-123"

    def __init__(self):
        self.messages: list[str] = []

    def send_message(self, text: str):
        self.messages.append(text)
        return TelegramSendReceipt(chat_id=self.chat_id, message_id=98 + len(self.messages))


def _videos(count: int = 3):
    return [
        video()
        .with_id(f"v{i}")
        .with_title(f"Video {i}")
        .with_channel(f"Channel {i}", f"ch{i}")
        .with_description(
            "This episode covers a concrete founder workflow for using AI tools in product research."
        )
        .build()
        for i in range(1, count + 1)
    ]


def _delivery_record(selected_video_ids: list[str], dry_run: bool = False) -> DeliveryRecord:
    return DeliveryRecord(
        delivered_at="2026-05-06T01:00:00+00:00",
        dry_run=dry_run,
        skill_name="production-skill",
        skill_version="2.1",
        strategy="recency",
        production_skill_path="/fake/SKILL.md",
        cache_path="adas/test_sets/video_cache_w1.json",
        feedback_path="adas/test_sets/feedback.json",
        telegram_chat_id="chat-123",
        telegram_message_id=42 if not dry_run else None,
        selected_video_ids=selected_video_ids,
    )


def _write_cache(path, fetched_at: str, count: int = 3) -> None:
    path.write_text(
        json.dumps(
            {
                "fetched_at": fetched_at,
                "count": count,
                "videos": [{"video_id": f"v{i}"} for i in range(count)],
            }
        )
    )


def _gate(now: datetime, **overrides) -> CacheFreshnessGate:
    return CacheFreshnessGate(
        cache_repository=VideoCacheRepository(),
        now_factory=lambda: now,
        **overrides,
    )


_NOW = datetime(2026, 5, 23, 4, 30, tzinfo=timezone.utc)


class TestCacheFreshnessGate:
    def test_fresh_cache_yields_no_notes(self, tmp_path):
        cache = tmp_path / "cache.json"
        _write_cache(cache, "2026-05-23T00:30:00+00:00")  # 4h old

        assert _gate(_NOW).evaluate(str(cache)) == []

    def test_moderately_stale_cache_warns_without_failing(self, tmp_path):
        cache = tmp_path / "cache.json"
        _write_cache(cache, "2026-05-22T00:30:00+00:00")  # 28h old

        notes = _gate(_NOW).evaluate(str(cache))

        assert len(notes) == 1
        assert "28.0h old" in notes[0]
        assert "refresh may have failed" in notes[0]

    def test_severely_stale_cache_raises(self, tmp_path):
        cache = tmp_path / "cache.json"
        _write_cache(cache, "2026-05-20T00:30:00+00:00")  # 76h old

        with pytest.raises(StaleCacheError, match="Refusing to deliver a stale digest"):
            _gate(_NOW).evaluate(str(cache))

    def test_unknown_freshness_when_timestamp_missing(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"videos": [{"video_id": "v0"}]}))

        notes = _gate(_NOW).evaluate(str(cache))

        assert notes == [
            "Cache freshness unknown: missing or unreadable 'fetched_at' timestamp; "
            "delivering on a best-effort basis."
        ]

    def test_thresholds_are_configurable(self, tmp_path):
        cache = tmp_path / "cache.json"
        _write_cache(cache, "2026-05-23T00:30:00+00:00")  # 4h old

        with pytest.raises(StaleCacheError):
            _gate(_NOW, stale_warn_hours=1.0, max_age_hours=2.0).evaluate(str(cache))


def test_delivery_appends_stale_cache_note(tmp_path):
    cache = tmp_path / "video_cache_w1.json"
    _write_cache(cache, "2026-05-22T00:30:00+00:00")  # 28h old at _NOW
    request = make_request(videos=_videos(), skill_doc=skill().build())
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2", "v3"]),
        formatter=TelegramDigestFormatter(
            now_factory=lambda: datetime(2026, 5, 23, 4, 30, tzinfo=timezone.utc)
        ),
        delivery_log_store=DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path),
        delivered_at_factory=lambda: "2026-05-23T04:30:00+00:00",
        freshness_gate=_gate(_NOW),
    )

    result = service.deliver(
        cache_path=str(cache),
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
        feedback_path=None,
    )

    assert any("refresh may have failed" in note for note in result.execution_notes)


def test_delivery_aborts_on_severely_stale_cache(tmp_path):
    cache = tmp_path / "video_cache_w1.json"
    _write_cache(cache, "2026-05-20T00:30:00+00:00")  # 76h old at _NOW
    request = make_request(videos=_videos(), skill_doc=skill().build())
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2", "v3"]),
        delivery_log_store=DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path),
        freshness_gate=_gate(_NOW),
    )

    with pytest.raises(StaleCacheError):
        service.deliver(
            cache_path=str(cache),
            production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
            feedback_path=None,
        )


def test_dry_run_writes_delivery_log(tmp_path):
    skill_doc = skill().with_name("production-skill").build()
    skill_doc.version = "2.1"
    request = make_request(videos=_videos(), skill_doc=skill_doc)
    store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2", "v3"]),
        formatter=TelegramDigestFormatter(
            now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
        ),
        delivery_log_store=store,
        delivered_at_factory=lambda: "2026-05-07T01:00:00+00:00",
    )

    result = service.deliver(
        cache_path="adas/test_sets/video_cache_w1.json",
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
        feedback_path="adas/test_sets/feedback.json",
        send=False,
    )

    assert result.status == "dry_run"
    assert result.telegram_message_id is None
    history = json.loads(store.path.read_text())["history"]
    assert history[0]["dry_run"] is True
    assert history[0]["skill_version"] == "2.1"
    assert history[0]["selected_video_ids"] == ["v1", "v2", "v3"]


def test_send_calls_telegram_and_persists_message_id(tmp_path):
    request = make_request(videos=_videos(), skill_doc=skill().build())
    sender = _StubSender()
    store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2", "v3"]),
        formatter=TelegramDigestFormatter(
            now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
        ),
        sender=sender,
        delivery_log_store=store,
        delivered_at_factory=lambda: "2026-05-07T01:00:00+00:00",
    )

    result = service.deliver(
        cache_path="adas/test_sets/video_cache_w1.json",
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
        send=True,
    )

    assert result.status == "sent"
    assert result.telegram_message_id == 99
    assert result.telegram_message_ids == [99, 100, 101]
    assert result.pick_message_ids == {"v1": 99, "v2": 100, "v3": 101}
    assert result.telegram_chat_id == "chat-123"
    assert len(sender.messages) == 3
    persisted = json.loads(store.path.read_text())["history"][0]
    assert persisted["telegram_message_id"] == 99
    assert persisted["telegram_message_ids"] == [99, 100, 101]
    assert persisted["pick_message_ids"] == {"v1": 99, "v2": 100, "v3": 101}


def test_delivery_allows_short_digest(tmp_path):
    request = make_request(videos=_videos(), skill_doc=skill().build())
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2"]),
        delivery_log_store=DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path),
    )

    result = service.deliver(
        cache_path="adas/test_sets/video_cache_w1.json",
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
    )

    assert result.selected_video_ids == ["v1", "v2"]
    assert any("sending a short digest" in note for note in result.execution_notes)


def test_delivery_excludes_previously_sent_video_ids(tmp_path):
    request = make_request(videos=_videos(6), skill_doc=skill().build())
    store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
    store.append(_delivery_record(["v1", "v2", "v3"]))
    service = ProductionDigestService(
        evaluator=_FirstThreeEvaluator(request),
        delivery_log_store=store,
        formatter=TelegramDigestFormatter(
            now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
        ),
        delivered_at_factory=lambda: "2026-05-07T01:00:00+00:00",
    )

    result = service.deliver(
        cache_path="adas/test_sets/video_cache_w1.json",
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
    )

    assert result.selected_video_ids == ["v4", "v5", "v6"]
    assert "Excluded 3 previously delivered video(s)." in result.execution_notes


def test_delivery_does_not_treat_dry_runs_as_seen(tmp_path):
    request = make_request(videos=_videos(6), skill_doc=skill().build())
    store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
    store.append(_delivery_record(["v1", "v2", "v3"], dry_run=True))
    service = ProductionDigestService(
        evaluator=_FirstThreeEvaluator(request),
        delivery_log_store=store,
        formatter=TelegramDigestFormatter(
            now_factory=lambda: datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)
        ),
        delivered_at_factory=lambda: "2026-05-07T01:00:00+00:00",
    )

    result = service.deliver(
        cache_path="adas/test_sets/video_cache_w1.json",
        production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
    )

    assert result.selected_video_ids == ["v1", "v2", "v3"]
