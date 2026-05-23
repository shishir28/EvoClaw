"""Tests for the compact daily status report."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from feedback.store import FeedbackStore
from status_report import DailyStatusReport, DailyStatusReporter, JobFailure
from telegram.delivery_log import DeliveryLogStore
from telegram.models import DeliveryRecord

_NOW = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
_TODAY = "2026-05-23"


def _write_cache(path, fetched_at: str | None, count: int = 87) -> None:
    payload: dict = {"count": count, "videos": [{"video_id": f"v{i}"} for i in range(count)]}
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    path.write_text(json.dumps(payload))


def _delivery_record(
    *,
    delivered_at: str,
    dry_run: bool = False,
    selected=("v1", "v2", "v3"),
    message_ids=(99, 100, 101),
    excluded_note: str | None = "Excluded 3 previously delivered video(s).",
) -> DeliveryRecord:
    notes = [excluded_note] if excluded_note else []
    return DeliveryRecord(
        delivered_at=delivered_at,
        dry_run=dry_run,
        skill_name="production-skill",
        skill_version="2.1",
        strategy="recency",
        production_skill_path="/fake/SKILL.md",
        cache_path="adas/test_sets/video_cache_w1.json",
        feedback_path=None,
        telegram_chat_id="chat-123",
        telegram_message_id=message_ids[0] if message_ids else None,
        selected_video_ids=list(selected),
        telegram_message_ids=list(message_ids),
        pick_message_ids=dict(zip(selected, message_ids)),
        execution_notes=notes,
    )


def _write_feedback(path, date: str, reactions: list[str | None]) -> None:
    picks = [{"video_id": f"v{i}", "reaction": r} for i, r in enumerate(reactions)]
    path.write_text(json.dumps({"history": [{"date": date, "picks": picks}]}))


def _write_cron_log(logs_dir, name: str, timestamp: str, exit_code: int) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / f"{name}-{timestamp}.log").write_text(
        f"# EvoClaw job: {name}\nsome output\n\n# exit code: {exit_code}\n"
    )


def _reporter(tmp_path, **overrides) -> DailyStatusReporter:
    delivery = tmp_path / "delivery_log.json"
    feedback = tmp_path / "feedback.json"
    return DailyStatusReporter(
        cache_path=str(overrides.pop("cache_path", tmp_path / "cache.json")),
        delivery_log_store=DeliveryLogStore(delivery, safe_base=tmp_path),
        feedback_store=FeedbackStore(str(feedback), safe_base=tmp_path),
        cron_logs_dir=overrides.pop("cron_logs_dir", tmp_path / "logs"),
        now_factory=lambda: _NOW,
        **overrides,
    )


class TestDailyStatusReporter:
    def test_fresh_cache_with_full_delivery(self, tmp_path):
        _write_cache(tmp_path / "cache.json", "2026-05-23T00:30:00+00:00", count=87)
        store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
        store.append(_delivery_record(delivered_at="2026-05-23T04:30:00+00:00"))
        _write_feedback(tmp_path / "feedback.json", _TODAY, ["👍", "👎", None])

        report = _reporter(tmp_path).build()

        assert report.date == _TODAY
        assert report.cache_age_hours == 8.5
        assert report.videos_fetched == 87
        assert report.digest_sent is True
        assert report.selected_video_ids == ["v1", "v2", "v3"]
        assert report.delivery_message_ids == [99, 100, 101]
        assert report.excluded_repeats == 3
        assert report.reactions_captured == 2
        assert report.reactions_breakdown == {"👍": 1, "👎": 1}
        assert report.failures == []

    def test_dry_runs_and_other_days_are_ignored_for_delivery(self, tmp_path):
        _write_cache(tmp_path / "cache.json", "2026-05-23T00:30:00+00:00")
        store = DeliveryLogStore(tmp_path / "delivery_log.json", safe_base=tmp_path)
        store.append(_delivery_record(delivered_at="2026-05-22T04:30:00+00:00"))  # yesterday
        store.append(_delivery_record(delivered_at="2026-05-23T04:30:00+00:00", dry_run=True))

        report = _reporter(tmp_path).build()

        assert report.digest_sent is False
        assert report.selected_video_ids == []
        assert report.excluded_repeats == 0

    def test_missing_cache_reports_unknown_age(self, tmp_path):
        report = _reporter(tmp_path).build()

        assert report.cache_exists is False
        assert report.cache_age_hours is None
        assert report.videos_fetched == 0

    def test_failures_scanned_from_cron_logs_for_the_day(self, tmp_path):
        _write_cache(tmp_path / "cache.json", "2026-05-23T00:30:00+00:00")
        logs = tmp_path / "logs"
        _write_cron_log(logs, "morning-digest", "20260523T043000Z", exit_code=3)
        _write_cron_log(logs, "refresh-video-cache", "20260523T003000Z", exit_code=0)
        _write_cron_log(logs, "morning-digest", "20260522T043000Z", exit_code=2)  # other day

        report = _reporter(tmp_path).build()

        assert len(report.failures) == 1
        assert report.failures[0] == JobFailure(
            job="morning-digest", exit_code=3, log="morning-digest-20260523T043000Z.log"
        )

    def test_cache_without_timestamp_reports_unknown_age_but_keeps_count(self, tmp_path):
        _write_cache(tmp_path / "cache.json", fetched_at=None, count=12)

        report = _reporter(tmp_path).build()

        assert report.cache_exists is True
        assert report.cache_age_hours is None
        assert report.videos_fetched == 12


class TestStatusLogWrite:
    def test_write_appends_one_jsonl_line(self, tmp_path):
        _write_cache(tmp_path / "cache.json", "2026-05-23T00:30:00+00:00")
        reporter = _reporter(tmp_path)
        log_path = tmp_path / "daily_status.jsonl"

        report = reporter.build()
        written = reporter.write(report, status_log_path=str(log_path))

        lines = log_path.read_text().splitlines()
        assert written == log_path
        assert len(lines) == 1
        assert json.loads(lines[0])["date"] == _TODAY

    def test_rerunning_same_date_replaces_its_line(self, tmp_path):
        _write_cache(tmp_path / "cache.json", "2026-05-23T00:30:00+00:00")
        reporter = _reporter(tmp_path)
        log_path = tmp_path / "daily_status.jsonl"
        log_path.write_text(json.dumps({"date": "2026-05-22", "cache": {}}) + "\n")

        reporter.write(reporter.build(), status_log_path=str(log_path))
        reporter.write(reporter.build(), status_log_path=str(log_path))

        lines = log_path.read_text().splitlines()
        dates = [json.loads(line)["date"] for line in lines]
        assert dates == ["2026-05-22", _TODAY]


class TestSummaryRendering:
    def _report(self, **overrides) -> DailyStatusReport:
        defaults = dict(
            date=_TODAY,
            cache_exists=True,
            cache_age_hours=8.5,
            cache_fetched_at="2026-05-23T00:30:00+00:00",
            videos_fetched=87,
            digest_sent=True,
            selected_video_ids=["v1", "v2", "v3"],
            delivery_message_ids=[99, 100, 101],
            excluded_repeats=3,
            reactions_captured=2,
            reactions_breakdown={"👍": 1, "👎": 1},
            failures=[],
        )
        defaults.update(overrides)
        return DailyStatusReport(**defaults)

    def test_summary_is_compact_and_covers_all_signals(self):
        summary = self._report().to_summary()

        assert "8.5h old · 87 videos" in summary
        assert "[v1, v2, v3]" in summary
        assert "[99, 100, 101]" in summary
        assert "excluded 3 repeat(s)" in summary
        assert "2 captured" in summary
        assert "failures  : none" in summary

    def test_summary_lists_failures(self):
        summary = self._report(
            failures=[JobFailure("morning-digest", 3, "morning-digest-20260523T043000Z.log")]
        ).to_summary()

        assert "1 job(s) failed" in summary
        assert "morning-digest (exit 3)" in summary

    def test_summary_handles_no_delivery(self):
        summary = self._report(
            digest_sent=False, selected_video_ids=[], delivery_message_ids=[]
        ).to_summary()

        assert "not delivered today" in summary
