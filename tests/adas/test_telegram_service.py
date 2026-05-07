"""Tests for production digest delivery orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from adas.telegram.delivery_log import DeliveryLogStore
from adas.telegram.formatter import TelegramDigestFormatter
from adas.telegram.models import TelegramSendReceipt
from adas.telegram.service import ProductionDigestService
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


class _StubSender:
    chat_id = "chat-123"

    def __init__(self):
        self.messages: list[str] = []

    def send_message(self, text: str):
        self.messages.append(text)
        return TelegramSendReceipt(chat_id=self.chat_id, message_id=99)


def _videos():
    return [
        video()
        .with_id(f"v{i}")
        .with_title(f"Video {i}")
        .with_channel(f"Channel {i}", f"ch{i}")
        .with_description(
            "This episode covers a concrete founder workflow for using AI tools in product research."
        )
        .build()
        for i in range(1, 4)
    ]


def test_dry_run_writes_delivery_log(tmp_path):
    skill_doc = skill().with_name("production-skill").build()
    skill_doc.version = "2.1"
    request = make_request(videos=_videos(), skill_doc=skill_doc)
    store = DeliveryLogStore(tmp_path / "delivery_log.json")
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
    store = DeliveryLogStore(tmp_path / "delivery_log.json")
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
    assert result.telegram_chat_id == "chat-123"
    assert len(sender.messages) == 1
    assert json.loads(store.path.read_text())["history"][0]["telegram_message_id"] == 99


def test_delivery_requires_exactly_three_picks(tmp_path):
    request = make_request(videos=_videos(), skill_doc=skill().build())
    service = ProductionDigestService(
        evaluator=_StubEvaluator(request, ["v1", "v2"]),
        delivery_log_store=DeliveryLogStore(tmp_path / "delivery_log.json"),
    )

    with pytest.raises(ValueError, match="exactly 3 selected videos"):
        service.deliver(
            cache_path="adas/test_sets/video_cache_w1.json",
            production_skill_path=str(tmp_path / "skills" / "youtube-curator" / "SKILL.md"),
        )
