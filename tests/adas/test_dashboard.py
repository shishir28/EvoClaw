"""Tests for the local EvoClaw dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from adas.archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
from adas.archive_runtime.store import ArchiveStore
from adas.deployment.promoter import DeploymentRecord, DeploymentRecordStore
from adas.dashboard import DashboardDataBuilder, render_dashboard_html
from adas.feedback.store import FeedbackStore
from adas.status_report import DailyStatusReporter
from adas.telegram.delivery_log import DeliveryLogStore
from adas.telegram.models import DeliveryRecord, TelegramDigestPick

_NOW = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)


def _write_cache(path, fetched_at: str | None, count: int = 87) -> None:
    payload: dict = {"count": count, "videos": [{"video_id": f"v{i}"} for i in range(count)]}
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    path.write_text(json.dumps(payload))


def _write_feedback(path, history: list[dict]) -> None:
    path.write_text(json.dumps({"history": history}))


def _write_status_log(path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _delivery_record(delivered_at: str) -> DeliveryRecord:
    return DeliveryRecord(
        delivered_at=delivered_at,
        dry_run=False,
        skill_name="production-skill",
        skill_version="2.2",
        strategy="recency",
        production_skill_path="/tmp/SKILL.md",
        cache_path="adas/test_sets/video_cache_w1.json",
        feedback_path=None,
        telegram_chat_id="chat-1",
        telegram_message_id=100,
        selected_video_ids=["v1", "v2", "v3"],
        telegram_message_ids=[100, 101, 102],
        pick_message_ids={"v1": 100, "v2": 101, "v3": 102},
        picks=[
            TelegramDigestPick(1, "v1", "Video One", "Channel A", "https://youtu.be/1", 9, "3h", "High signal"),
            TelegramDigestPick(2, "v2", "Video Two", "Channel B", "https://youtu.be/2", 12, "6h", "Useful tactics"),
        ],
        execution_notes=["Excluded 1 previously delivered video(s)."],
    )


def _entry(skill_id: str, score: float, source_type: str = "meta-agent", use_llm: bool = True) -> ArchiveIndexEntry:
    return ArchiveIndexEntry(
        skill_id=skill_id,
        skill_name=f"skill-{skill_id}",
        source_type=source_type,
        archive_key=f"{source_type}:{skill_id}",
        archive_path=skill_id,
        archived_at="2026-05-23T01:00:00+00:00",
        origin_skill_path=f"/tmp/{skill_id}.md",
        status="scored",
        total_score=score,
        strategy="recency",
        context={"use_llm_judging": use_llm},
    )


def _builder(tmp_path) -> DashboardDataBuilder:
    cache_path = tmp_path / "cache.json"
    delivery_path = tmp_path / "delivery_log.json"
    feedback_path = tmp_path / "feedback.json"
    status_log_path = tmp_path / "daily_status.jsonl"
    archive_dir = tmp_path / "archive"
    deployment_path = tmp_path / "deployment.json"

    _write_cache(cache_path, "2026-05-23T00:30:00+00:00", count=87)
    delivery_store = DeliveryLogStore(delivery_path, safe_base=tmp_path)
    delivery_store.append(_delivery_record("2026-05-23T04:30:00+00:00"))
    _write_feedback(
        feedback_path,
        [
            {"date": "2026-05-22", "picks": [{"video_id": "v1", "reaction": "👍"}]},
            {
                "date": "2026-05-23",
                "picks": [
                    {"video_id": "v2", "reaction": "👍"},
                    {"video_id": "v3", "reaction": "👎"},
                ],
            },
        ],
    )
    _write_status_log(
        status_log_path,
        [
            {
                "date": "2026-05-22",
                "cache": {
                    "exists": True,
                    "age_hours": 9.1,
                    "fetched_at": "2026-05-22T00:30:00+00:00",
                    "videos_fetched": 75,
                },
                "digest": {
                    "sent": True,
                    "selected_video_ids": ["x1"],
                    "delivery_message_ids": [1],
                    "excluded_repeats": 0,
                },
                "reactions": {"captured": 1, "breakdown": {"👍": 1}},
                "failures": [
                    {
                        "job": "morning-digest",
                        "exit_code": 2,
                        "log": "morning-digest-20260522T043000Z.log",
                    }
                ],
            }
        ],
    )
    archive = ArchiveStore(str(archive_dir))
    archive.save_index(
        ArchiveIndex(
            best_skill_id="skill_002",
            best_score=8.2,
            skills=[
                _entry("skill_001", 7.5, source_type="baseline", use_llm=True),
                _entry("skill_002", 8.2, source_type="meta-agent", use_llm=True),
                _entry("skill_003", 6.0, source_type="meta-agent", use_llm=False),
            ],
        )
    )
    deployment_store = DeploymentRecordStore(deployment_path)
    deployment_store.save(
        DeploymentRecord(
            deployed_skill_id="skill_002",
            deployed_score=8.2,
            deployed_at="2026-05-23T02:00:00+00:00",
            source_skill_path="/tmp/skill_002/SKILL.md",
            production_skill_path="/tmp/prod/SKILL.md",
            previous_skill_id="skill_001",
            previous_score=7.5,
        )
    )
    deployment_store.append_history(
        DeploymentRecord(
            deployed_skill_id="skill_001",
            deployed_score=7.5,
            deployed_at="2026-05-22T02:00:00+00:00",
            source_skill_path="/tmp/skill_001/SKILL.md",
            production_skill_path="/tmp/prod/SKILL.md",
            previous_skill_id=None,
            previous_score=None,
        )
    )
    current_record = deployment_store.load()
    assert current_record is not None
    deployment_store.append_history(current_record)

    feedback_store = FeedbackStore(str(feedback_path), safe_base=tmp_path)
    reporter = DailyStatusReporter(
        cache_path=str(cache_path),
        delivery_log_store=delivery_store,
        feedback_store=feedback_store,
        cron_logs_dir=tmp_path / "logs",
        now_factory=lambda: _NOW,
    )
    return DashboardDataBuilder(
        cache_path=str(cache_path),
        status_reporter=reporter,
        delivery_log_store=delivery_store,
        feedback_store=feedback_store,
        archive_store=archive,
        deployment_store=deployment_store,
        status_log_path=str(status_log_path),
        now_factory=lambda: _NOW,
    )


class TestDashboardDataBuilder:
    def test_builds_dashboard_snapshot_from_existing_artifacts(self, tmp_path):
        snapshot = _builder(tmp_path).build()

        assert snapshot.current_status.date == "2026-05-23"
        assert snapshot.current_status.videos_fetched == 87
        assert len(snapshot.recent_deliveries) == 1
        assert snapshot.recent_deliveries[0].picks[0].title == "Video One"
        assert snapshot.reaction_trends[-1].date == "2026-05-23"
        assert snapshot.reaction_trends[-1].positive == 1
        assert snapshot.reaction_trends[-1].negative == 1
        assert snapshot.archive_leaderboard[0]["skill_id"] == "skill_002"
        assert snapshot.archive_leaderboard[0]["use_llm_judging"] is True
        assert snapshot.recent_failures[0].job == "morning-digest"
        assert snapshot.promotion_history[0].deployed_skill_id == "skill_002"

    def test_falls_back_to_current_deployment_when_history_log_is_missing(self, tmp_path):
        builder = _builder(tmp_path)
        builder._deployment_store.history_path.unlink()

        snapshot = builder.build()

        assert len(snapshot.promotion_history) == 1
        assert snapshot.promotion_history[0].deployed_skill_id == "skill_002"


class TestDashboardHtml:
    def test_html_contains_requested_sections(self, tmp_path):
        html = render_dashboard_html(_builder(tmp_path).build())

        assert "Cache Health" in html
        assert "Daily Picks" in html
        assert "Reaction Trends" in html
        assert "Archive Leaderboard" in html
        assert "Promotion History" in html
        assert "Video One" in html
        assert "skill_002" in html
