"""CLI tests for the Step 11 Telegram digest command."""

from __future__ import annotations

import json

import adas.telegram.service as telegram_service
from adas.telegram.models import DigestDeliveryResult, TelegramDigestPick


def test_send_flag_forwarded(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def _fake_send_digest(**kwargs):
        calls.append(kwargs)
        return DigestDeliveryResult(
            status="sent",
            dry_run=False,
            skill_name="prod",
            skill_version="1.0",
            strategy="recency",
            production_skill_path=kwargs["production_skill_path"],
            cache_path=kwargs["cache_path"],
            feedback_path=kwargs["feedback_path"],
            delivery_log_path=kwargs["delivery_log_path"],
            telegram_chat_id="chat-1",
            telegram_message_id=101,
            selected_video_ids=["v1", "v2", "v3"],
            picks=[
                TelegramDigestPick(
                    rank=1,
                    video_id="v1",
                    title="Video 1",
                    channel="Channel 1",
                    url="https://www.youtube.com/watch?v=v1",
                    duration_minutes=10,
                    age_label="2 hours ago",
                    why_watch="Why watch",
                )
            ],
            execution_notes=[],
            message_text="hello",
        )

    monkeypatch.setattr(telegram_service, "send_digest", _fake_send_digest)
    monkeypatch.setattr(
        "sys.argv",
        [
            "telegram_digest.py",
            "--cache",
            "adas/test_sets/video_cache_w1.json",
            "--skill",
            "/tmp/skills/youtube-curator/SKILL.md",
            "--delivery-log",
            "/tmp/skills/youtube-curator/delivery_log.json",
            "--send",
        ],
    )

    telegram_service.main()

    assert calls == [
        {
            "cache_path": "adas/test_sets/video_cache_w1.json",
            "production_skill_path": "/tmp/skills/youtube-curator/SKILL.md",
            "feedback_path": telegram_service.FEEDBACK_FILE,
            "delivery_log_path": "/tmp/skills/youtube-curator/delivery_log.json",
            "send": True,
        }
    ]
    assert json.loads(capsys.readouterr().out)["status"] == "sent"
