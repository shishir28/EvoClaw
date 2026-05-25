"""Compact daily status report for the EvoClaw pipeline.

Aggregates a single day's operational signals — cache freshness, videos
fetched, repeats excluded, picks delivered with their Telegram message IDs,
reactions captured, and any cron job failures — into a one-glance summary plus
an append-only JSONL log. The four nightly jobs each leave their own structured
artifact (cache file, delivery log, feedback file, cron job logs); this module
reads those after the fact rather than instrumenting each job, so it stays
decoupled and can be re-run for any past date.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from adas.config import BASE_DIR, DELIVERY_LOG, FEEDBACK_FILE, TEST_SETS_DIR
from adas.evaluation.models import FeedbackEntry
from adas.feedback.store import FeedbackStore
from adas.telegram.delivery_log import DeliveryLogStore
from adas.telegram.models import DeliveryRecord
from adas.utils.paths import write_text_atomic
from adas.youtube_fetcher import VideoCacheRepository


# Production delivery records carry an execution note like
# "Excluded 3 previously delivered video(s)." — pull the count back out of it.
_EXCLUDED_RE = re.compile(r"Excluded (\d+) previously delivered")

# Cron logs are named "{job}-{YYYYMMDD}T{HHMMSS}Z.log" and end with a
# "# exit code: N" trailer written by cron/runner.py.
_LOG_NAME_RE = re.compile(r"^(?P<job>.+)-(?P<date>\d{8})T\d{6}Z\.log$")
_EXIT_CODE_RE = re.compile(r"# exit code: (-?\d+)")

_DEFAULT_CACHE_NAME = "video_cache_w1.json"
_STATUS_LOG_NAME = "daily_status.jsonl"


@dataclass(frozen=True, slots=True)
class JobFailure:
    """One cron job that exited non-zero on the reporting day."""

    job: str
    exit_code: int
    log: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DailyStatusReport:
    """The day's pipeline signals, ready to print or persist as one JSON line."""

    date: str
    cache_exists: bool
    cache_age_hours: float | None
    cache_fetched_at: str | None
    videos_fetched: int
    digest_sent: bool
    selected_video_ids: list[str]
    delivery_message_ids: list[int]
    excluded_repeats: int
    reactions_captured: int
    reactions_breakdown: dict[str, int]
    failures: list[JobFailure]

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "cache": {
                "exists": self.cache_exists,
                "age_hours": (
                    round(self.cache_age_hours, 1)
                    if self.cache_age_hours is not None
                    else None
                ),
                "fetched_at": self.cache_fetched_at,
                "videos_fetched": self.videos_fetched,
            },
            "digest": {
                "sent": self.digest_sent,
                "selected_video_ids": list(self.selected_video_ids),
                "delivery_message_ids": list(self.delivery_message_ids),
                "excluded_repeats": self.excluded_repeats,
            },
            "reactions": {
                "captured": self.reactions_captured,
                "breakdown": dict(self.reactions_breakdown),
            },
            "failures": [failure.to_dict() for failure in self.failures],
        }

    def to_summary(self) -> str:
        """Render a compact, human-readable multi-line block."""
        if self.cache_age_hours is not None:
            cache = f"{self.cache_age_hours:.1f}h old · {self.videos_fetched} videos"
            if self.cache_fetched_at:
                cache += f" · fetched {self.cache_fetched_at}"
        elif self.cache_exists:
            cache = f"{self.videos_fetched} videos · age unknown (no timestamp)"
        else:
            cache = "missing"

        if self.digest_sent:
            ids = ", ".join(self.selected_video_ids) or "—"
            msgs = ", ".join(str(m) for m in self.delivery_message_ids) or "—"
            digest = (
                f"sent · {len(self.selected_video_ids)} picks [{ids}] · "
                f"msg ids [{msgs}] · excluded {self.excluded_repeats} repeat(s)"
            )
        else:
            digest = "not delivered today"

        if self.reactions_captured:
            breakdown = " ".join(
                f"{emoji} {count}" for emoji, count in sorted(self.reactions_breakdown.items())
            )
            reactions = f"{self.reactions_captured} captured ({breakdown})"
        else:
            reactions = "none captured"

        if self.failures:
            failures = "\n".join(
                f"    - {failure.job} (exit {failure.exit_code}) [{failure.log}]"
                for failure in self.failures
            )
            failures = f"{len(self.failures)} job(s) failed:\n{failures}"
        else:
            failures = "none"

        return (
            f"EvoClaw daily status — {self.date}\n"
            f"  cache     : {cache}\n"
            f"  digest    : {digest}\n"
            f"  reactions : {reactions}\n"
            f"  failures  : {failures}"
        )


@dataclass(slots=True)
class DailyStatusReporter:
    """Gather a :class:`DailyStatusReport` from on-disk job artifacts."""

    cache_path: str | None = None
    delivery_log_store: DeliveryLogStore | None = None
    feedback_store: FeedbackStore | None = None
    cache_repository: VideoCacheRepository | None = None
    cron_logs_dir: Path | None = None
    now_factory: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if self.cache_path is None:
            self.cache_path = str(Path(TEST_SETS_DIR) / _DEFAULT_CACHE_NAME)
        if self.delivery_log_store is None:
            self.delivery_log_store = DeliveryLogStore(DELIVERY_LOG)
        if self.feedback_store is None:
            self.feedback_store = FeedbackStore(FEEDBACK_FILE)
        if self.cache_repository is None:
            self.cache_repository = VideoCacheRepository()
        if self.cron_logs_dir is None:
            self.cron_logs_dir = Path(BASE_DIR) / "cron" / "logs"
        if self.now_factory is None:
            self.now_factory = lambda: datetime.now(timezone.utc)

    def build(self, date: str | None = None) -> DailyStatusReport:
        """Assemble the report for ``date`` (UTC ``YYYY-MM-DD``; default today)."""
        now = self.now_factory()
        target_date = date or now.strftime("%Y-%m-%d")

        meta = self.cache_repository.load_metadata(self.cache_path, now=now)
        record = self._latest_delivery(target_date)
        captured, breakdown = self._reactions(target_date)
        failures = self._failures(target_date)

        return DailyStatusReport(
            date=target_date,
            cache_exists=meta.exists,
            cache_age_hours=meta.age_hours,
            cache_fetched_at=meta.fetched_at.isoformat() if meta.fetched_at else None,
            videos_fetched=meta.count,
            digest_sent=record is not None,
            selected_video_ids=list(record.selected_video_ids) if record else [],
            delivery_message_ids=list(record.telegram_message_ids) if record else [],
            excluded_repeats=self._excluded_repeats(record),
            reactions_captured=captured,
            reactions_breakdown=breakdown,
            failures=failures,
        )

    def write(self, report: DailyStatusReport, status_log_path: str | None = None) -> Path:
        """Append the report to the JSONL status log, replacing any line for its date."""
        path = Path(status_log_path) if status_log_path else self._default_status_log()
        existing = path.read_text().splitlines() if path.exists() else []
        kept = [
            line
            for line in existing
            if line.strip() and not self._line_matches_date(line, report.date)
        ]
        kept.append(json.dumps(report.to_dict(), ensure_ascii=False))
        write_text_atomic(path, "\n".join(kept) + "\n")
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _latest_delivery(self, target_date: str) -> DeliveryRecord | None:
        """Return the last live (non-dry-run) delivery recorded on ``target_date``."""
        match: DeliveryRecord | None = None
        for record in self.delivery_log_store.load_history():
            if record.dry_run:
                continue
            if record.delivered_at.startswith(target_date):
                match = record
        return match

    @staticmethod
    def _excluded_repeats(record: DeliveryRecord | None) -> int:
        if record is None:
            return 0
        for note in record.execution_notes:
            found = _EXCLUDED_RE.search(note)
            if found:
                return int(found.group(1))
        return 0

    def _reactions(self, target_date: str) -> tuple[int, dict[str, int]]:
        """Count reactions recorded for ``target_date`` across all feedback entries."""
        breakdown: dict[str, int] = {}
        for entry in self.feedback_store.load_history():
            if entry.date != target_date:
                continue
            for pick in entry.picks:
                if pick.reaction:
                    breakdown[pick.reaction] = breakdown.get(pick.reaction, 0) + 1
        return sum(breakdown.values()), breakdown

    def _failures(self, target_date: str) -> list[JobFailure]:
        """Scan cron logs for jobs that exited non-zero on ``target_date``."""
        compact = target_date.replace("-", "")
        if not self.cron_logs_dir.exists():
            return []
        failures: list[JobFailure] = []
        for log_file in sorted(self.cron_logs_dir.glob("*.log")):
            name_match = _LOG_NAME_RE.match(log_file.name)
            if not name_match or name_match.group("date") != compact:
                continue
            exit_code = self._read_exit_code(log_file)
            if exit_code not in (None, 0):
                failures.append(
                    JobFailure(
                        job=name_match.group("job"),
                        exit_code=exit_code,
                        log=log_file.name,
                    )
                )
        return failures

    @staticmethod
    def _read_exit_code(log_file: Path) -> int | None:
        try:
            text = log_file.read_text()
        except OSError:
            return None
        matches = _EXIT_CODE_RE.findall(text)
        return int(matches[-1]) if matches else None

    @staticmethod
    def _line_matches_date(line: str, date: str) -> bool:
        try:
            return json.loads(line).get("date") == date
        except (json.JSONDecodeError, AttributeError):
            return False

    def _default_status_log(self) -> Path:
        return self.cron_logs_dir / _STATUS_LOG_NAME


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a compact daily status report for the EvoClaw pipeline.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="UTC date to report on (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="Path to the video cache JSON used to gauge freshness.",
    )
    parser.add_argument(
        "--status-log",
        default=None,
        help="Path to the JSONL status log to append to (default: cron/logs/daily_status.jsonl).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of the human-readable summary.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Print only; do not append to the status log.",
    )
    args = parser.parse_args()

    reporter = DailyStatusReporter(cache_path=args.cache)
    report = reporter.build(date=args.date)

    if not args.no_log:
        path = reporter.write(report, status_log_path=args.status_log)
        print(f"# status logged → {path}")

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.json else report.to_summary())


if __name__ == "__main__":
    main()
