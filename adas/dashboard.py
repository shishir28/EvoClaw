"""Local read-only dashboard for EvoClaw operations and learning state."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from .archive_runtime.store import ArchiveStore
    from .config import (
        ARCHIVE_DIR,
        BASE_DIR,
        CACHE_MAX_AGE_HOURS,
        CACHE_STALE_WARN_HOURS,
        DELIVERY_LOG,
        FEEDBACK_FILE,
        SKILL_PRODUCTION,
        TEST_SETS_DIR,
    )
    from .deployment.promoter import DeploymentRecord, DeploymentRecordStore
    from .feedback.store import FeedbackStore
    from .status_report import DailyStatusReport, DailyStatusReporter, JobFailure
    from .telegram.delivery_log import DeliveryLogStore
    from .telegram.models import DeliveryRecord
except ImportError:
    from archive_runtime.store import ArchiveStore
    from config import (
        ARCHIVE_DIR,
        BASE_DIR,
        CACHE_MAX_AGE_HOURS,
        CACHE_STALE_WARN_HOURS,
        DELIVERY_LOG,
        FEEDBACK_FILE,
        SKILL_PRODUCTION,
        TEST_SETS_DIR,
    )
    from deployment.promoter import DeploymentRecord, DeploymentRecordStore
    from feedback.store import FeedbackStore
    from status_report import DailyStatusReport, DailyStatusReporter, JobFailure
    from telegram.delivery_log import DeliveryLogStore
    from telegram.models import DeliveryRecord

_DEFAULT_CACHE_PATH = str(Path(TEST_SETS_DIR) / "video_cache_w1.json")
_DEFAULT_STATUS_LOG_PATH = str(Path(BASE_DIR) / "cron" / "logs" / "daily_status.jsonl")


@dataclass(frozen=True, slots=True)
class ReactionTrendPoint:
    date: str
    positive: int
    negative: int
    other: int

    @property
    def total(self) -> int:
        return self.positive + self.negative + self.other

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "positive": self.positive,
            "negative": self.negative,
            "other": self.other,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class FailureEvent:
    date: str
    job: str
    exit_code: int
    log: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    generated_at: str
    current_status: DailyStatusReport
    recent_status: list[DailyStatusReport]
    recent_deliveries: list[DeliveryRecord]
    reaction_trends: list[ReactionTrendPoint]
    archive_leaderboard: list[dict[str, Any]]
    recent_failures: list[FailureEvent]
    promotion_history: list[DeploymentRecord]
    current_deployment: DeploymentRecord | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "current_status": self.current_status.to_dict(),
            "recent_status": [report.to_dict() for report in self.recent_status],
            "recent_deliveries": [record.to_dict() for record in self.recent_deliveries],
            "reaction_trends": [trend.to_dict() for trend in self.reaction_trends],
            "archive_leaderboard": list(self.archive_leaderboard),
            "recent_failures": [failure.to_dict() for failure in self.recent_failures],
            "promotion_history": [record.to_dict() for record in self.promotion_history],
            "current_deployment": (
                self.current_deployment.to_dict() if self.current_deployment is not None else None
            ),
        }


class DashboardDataBuilder:
    def __init__(
        self,
        cache_path: str = _DEFAULT_CACHE_PATH,
        status_reporter: DailyStatusReporter | None = None,
        delivery_log_store: DeliveryLogStore | None = None,
        feedback_store: FeedbackStore | None = None,
        archive_store: ArchiveStore | None = None,
        deployment_store: DeploymentRecordStore | None = None,
        status_log_path: str = _DEFAULT_STATUS_LOG_PATH,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache_path = cache_path
        self._status_reporter = status_reporter or DailyStatusReporter(cache_path=cache_path)
        self._delivery_log_store = delivery_log_store or DeliveryLogStore(DELIVERY_LOG)
        self._feedback_store = feedback_store or FeedbackStore(FEEDBACK_FILE)
        self._archive_store = archive_store or ArchiveStore(ARCHIVE_DIR)
        self._deployment_store = deployment_store or DeploymentRecordStore(
            Path(SKILL_PRODUCTION).with_name("deployment.json")
        )
        self._status_log_path = Path(status_log_path)
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc))

    def build(self) -> DashboardSnapshot:
        current_status = self._status_reporter.build()
        recent_status = self._collect_recent_status(current_status)
        recent_deliveries = self._recent_deliveries(limit=5)
        reaction_trends = self._reaction_trends(limit=7)
        recent_failures = self._recent_failures(recent_status, limit=10)
        archive_leaderboard = self._archive_leaderboard(limit=10)
        current_deployment = self._deployment_store.load()
        promotion_history = self._promotion_history(current_deployment, limit=10)
        return DashboardSnapshot(
            generated_at=self._now_factory().isoformat(),
            current_status=current_status,
            recent_status=recent_status,
            recent_deliveries=recent_deliveries,
            reaction_trends=reaction_trends,
            archive_leaderboard=archive_leaderboard,
            recent_failures=recent_failures,
            promotion_history=promotion_history,
            current_deployment=current_deployment,
        )

    def _collect_recent_status(
        self,
        current_status: DailyStatusReport,
        limit: int = 7,
    ) -> list[DailyStatusReport]:
        reports_by_date = {current_status.date: current_status}
        if self._status_log_path.exists():
            for line in self._status_log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    report = _report_from_logged_json(json.loads(line))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
                reports_by_date.setdefault(report.date, report)
        reports = sorted(reports_by_date.values(), key=lambda item: item.date, reverse=True)
        return reports[:limit]

    def _recent_deliveries(self, limit: int) -> list[DeliveryRecord]:
        deliveries = [
            record
            for record in self._delivery_log_store.load_history()
            if not record.dry_run
        ]
        deliveries.sort(key=lambda item: item.delivered_at, reverse=True)
        return deliveries[:limit]

    def _reaction_trends(self, limit: int) -> list[ReactionTrendPoint]:
        trend_by_date: dict[str, ReactionTrendPoint] = {}
        for entry in self._feedback_store.load_history():
            positive = negative = other = 0
            for pick in entry.picks:
                if pick.reaction == "👍":
                    positive += 1
                elif pick.reaction == "👎":
                    negative += 1
                elif pick.reaction:
                    other += 1
            trend_by_date[entry.date] = ReactionTrendPoint(
                date=entry.date,
                positive=positive,
                negative=negative,
                other=other,
            )
        trends = sorted(trend_by_date.values(), key=lambda item: item.date)
        return trends[-limit:]

    @staticmethod
    def _recent_failures(reports: list[DailyStatusReport], limit: int) -> list[FailureEvent]:
        failures: list[FailureEvent] = []
        for report in reports:
            for failure in report.failures:
                failures.append(
                    FailureEvent(
                        date=report.date,
                        job=failure.job,
                        exit_code=failure.exit_code,
                        log=failure.log,
                    )
                )
        failures.sort(key=lambda item: (item.date, item.log), reverse=True)
        return failures[:limit]

    def _archive_leaderboard(self, limit: int) -> list[dict[str, Any]]:
        index = self._archive_store.load_index()
        entries = [entry for entry in index.skills if entry.total_score is not None]
        entries.sort(
            key=lambda item: (
                -float(item.total_score),
                item.archived_at or "",
                item.skill_id,
            )
        )
        leaderboard: list[dict[str, Any]] = []
        for rank, entry in enumerate(entries[:limit], start=1):
            context = dict(entry.context or {})
            leaderboard.append(
                {
                    "rank": rank,
                    "skill_id": entry.skill_id,
                    "skill_name": entry.skill_name,
                    "source_type": entry.source_type,
                    "strategy": entry.strategy,
                    "status": entry.status,
                    "total_score": entry.total_score,
                    "archived_at": entry.archived_at,
                    "use_llm_judging": context.get("use_llm_judging"),
                }
            )
        return leaderboard

    def _promotion_history(
        self,
        current_deployment: DeploymentRecord | None,
        limit: int,
    ) -> list[DeploymentRecord]:
        history = self._deployment_store.load_history()
        if not history and current_deployment is not None:
            history = [current_deployment]
        history.sort(key=lambda item: item.deployed_at, reverse=True)
        return history[:limit]


def _report_from_logged_json(payload: dict[str, Any]) -> DailyStatusReport:
    cache = payload.get("cache", {})
    digest = payload.get("digest", {})
    reactions = payload.get("reactions", {})
    failure_payloads = payload.get("failures", [])
    return DailyStatusReport(
        date=str(payload.get("date", "")),
        cache_exists=bool(cache.get("exists", False)),
        cache_age_hours=(
            float(cache["age_hours"]) if cache.get("age_hours") is not None else None
        ),
        cache_fetched_at=cache.get("fetched_at"),
        videos_fetched=int(cache.get("videos_fetched", 0) or 0),
        digest_sent=bool(digest.get("sent", False)),
        selected_video_ids=[str(video_id) for video_id in digest.get("selected_video_ids", [])],
        delivery_message_ids=[
            int(message_id) for message_id in digest.get("delivery_message_ids", [])
        ],
        excluded_repeats=int(digest.get("excluded_repeats", 0) or 0),
        reactions_captured=int(reactions.get("captured", 0) or 0),
        reactions_breakdown={
            str(name): int(count) for name, count in reactions.get("breakdown", {}).items()
        },
        failures=[
            JobFailure(
                job=str(item.get("job", "")),
                exit_code=int(item.get("exit_code", 0)),
                log=str(item.get("log", "")),
            )
            for item in failure_payloads
            if isinstance(item, dict)
        ],
    )


def render_dashboard_html(snapshot: DashboardSnapshot) -> str:
    max_reactions = max((trend.total for trend in snapshot.reaction_trends), default=0)
    current = snapshot.current_status
    cache_state = _cache_state(current)
    failure_label = f"{len(snapshot.recent_failures)} recent" if snapshot.recent_failures else "none"
    leaderboard_rows = "".join(_render_leaderboard_row(row) for row in snapshot.archive_leaderboard)
    delivery_blocks = "".join(_render_delivery(record) for record in snapshot.recent_deliveries)
    trend_rows = "".join(_render_trend(trend, max_reactions) for trend in snapshot.reaction_trends)
    failure_rows = "".join(_render_failure(failure) for failure in snapshot.recent_failures)
    promotion_rows = "".join(_render_promotion(record) for record in snapshot.promotion_history)
    status_rows = "".join(_render_status_row(report) for report in snapshot.recent_status)
    current_deployment = _render_current_deployment(snapshot.current_deployment)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta http-equiv=\"refresh\" content=\"60\">
  <title>EvoClaw Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffaf2;
      --panel-2: #f0e7d8;
      --ink: #172126;
      --muted: #6a6d63;
      --accent: #c06c2d;
      --danger: #b64535;
      --ok: #2f7a45;
      --border: #d7cab6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f8f3ea 0%, #efe4d1 100%); color: var(--ink); font: 15px/1.45 Georgia, 'Times New Roman', serif; }}
    header, main {{ width: min(1180px, calc(100vw - 32px)); margin: 0 auto; }}
    header {{ padding: 28px 0 20px; }}
    h1, h2, h3 {{ margin: 0; font-weight: 700; letter-spacing: 0; }}
    h1 {{ font-size: clamp(2rem, 3vw, 3.4rem); }}
    h2 {{ font-size: 1rem; text-transform: uppercase; color: var(--muted); margin-bottom: 14px; }}
    p {{ margin: 0; }}
    .lede {{ margin-top: 10px; color: var(--muted); max-width: 780px; }}
    .topline {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
    .pill {{ border: 1px solid var(--border); background: rgba(255,255,255,0.65); padding: 6px 10px; font-size: 0.85rem; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(12, minmax(0, 1fr)); }}
    section {{ background: rgba(255,250,242,0.88); border: 1px solid var(--border); padding: 18px; margin-bottom: 16px; }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-6 {{ grid-column: span 6; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .metric {{ background: var(--panel); border: 1px solid var(--border); padding: 14px; min-height: 120px; }}
    .metric .value {{ font-size: 2rem; margin-top: 8px; }}
    .metric .label {{ color: var(--muted); font-size: 0.82rem; text-transform: uppercase; }}
    .metric .detail {{ color: var(--muted); margin-top: 8px; }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--accent); }}
    .bad {{ color: var(--danger); }}
    .stack {{ display: grid; gap: 12px; }}
    .delivery {{ padding: 12px 0; border-top: 1px solid var(--border); }}
    .delivery:first-child {{ border-top: 0; padding-top: 0; }}
    .delivery-head {{ display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    .delivery-meta, .mini {{ color: var(--muted); font-size: 0.9rem; }}
    .pick-list {{ margin-top: 8px; display: grid; gap: 6px; }}
    .pick {{ background: var(--panel); border: 1px solid var(--border); padding: 8px 10px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 10px 8px; border-top: 1px solid var(--border); vertical-align: top; }}
    th {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; border-top: 0; }}
    .scorebar {{ height: 8px; background: var(--panel-2); overflow: hidden; margin-top: 6px; }}
    .scorebar > span {{ display: block; height: 100%; background: linear-gradient(90deg, #d88d46, #934b1f); }}
    .trendbar {{ display: flex; height: 10px; background: var(--panel-2); overflow: hidden; margin-top: 6px; }}
    .trendbar .pos {{ background: #3f8c57; }}
    .trendbar .neg {{ background: #b64535; }}
    .trendbar .other {{ background: #8b7f6d; }}
    .subtle {{ color: var(--muted); }}
    @media (max-width: 900px) {{
      .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 {{ grid-column: span 12; }}
      header, main {{ width: min(100vw - 20px, 1180px); }}
      .metric .value {{ font-size: 1.6rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>EvoClaw Dashboard</h1>
    <p class=\"lede\">Cache health, digest output, feedback drift, archive competition, failures, and deployment changes in one local view.</p>
    <div class=\"topline\">
      <span class=\"pill\">Generated {escape(_format_timestamp(snapshot.generated_at))}</span>
      <span class=\"pill\">Current date {escape(current.date)}</span>
      <span class=\"pill\">Failures {escape(failure_label)}</span>
      <span class=\"pill\">Promotions tracked {len(snapshot.promotion_history)}</span>
    </div>
  </header>
  <main>
    <div class=\"grid\">
      <section class=\"metric span-3\">
        <div class=\"label\">Cache Health</div>
        <div class=\"value {_severity_class(cache_state)}\">{escape(cache_state)}</div>
        <div class=\"detail\">{escape(_cache_detail(current))}</div>
      </section>
      <section class=\"metric span-3\">
        <div class=\"label\">Videos Fetched</div>
        <div class=\"value\">{current.videos_fetched}</div>
        <div class=\"detail\">Fetched at {escape(_format_timestamp(current.cache_fetched_at))}</div>
      </section>
      <section class=\"metric span-3\">
        <div class=\"label\">Daily Picks</div>
        <div class=\"value\">{len(current.selected_video_ids)}</div>
        <div class=\"detail\">Digest {'sent' if current.digest_sent else 'not sent'} · excluded {current.excluded_repeats} repeats</div>
      </section>
      <section class=\"metric span-3\">
        <div class=\"label\">Reactions Today</div>
        <div class=\"value\">{current.reactions_captured}</div>
        <div class=\"detail\">{escape(_breakdown_label(current.reactions_breakdown))}</div>
      </section>

      <section class=\"span-7\">
        <h2>Daily Picks</h2>
        <div class=\"stack\">{delivery_blocks or '<p class="subtle">No live deliveries recorded yet.</p>'}</div>
      </section>

      <section class=\"span-5\">
        <h2>Current Deployment</h2>
        {current_deployment}
      </section>

      <section class=\"span-6\">
        <h2>Reaction Trends</h2>
        <table>
          <thead><tr><th>Date</th><th>Signals</th><th>Total</th></tr></thead>
          <tbody>{trend_rows or '<tr><td colspan="3" class="subtle">No reactions captured yet.</td></tr>'}</tbody>
        </table>
      </section>

      <section class=\"span-6\">
        <h2>Status History</h2>
        <table>
          <thead><tr><th>Date</th><th>Cache</th><th>Digest</th><th>Reactions</th><th>Failures</th></tr></thead>
          <tbody>{status_rows}</tbody>
        </table>
      </section>

      <section class=\"span-8\">
        <h2>Archive Leaderboard</h2>
        <table>
          <thead><tr><th>Rank</th><th>Skill</th><th>Source</th><th>Score</th><th>Scoring</th><th>Archived</th></tr></thead>
          <tbody>{leaderboard_rows or '<tr><td colspan="6" class="subtle">No scored archive entries yet.</td></tr>'}</tbody>
        </table>
      </section>

      <section class=\"span-4\">
        <h2>Failures</h2>
        <table>
          <thead><tr><th>Date</th><th>Job</th><th>Exit</th></tr></thead>
          <tbody>{failure_rows or '<tr><td colspan="3" class="subtle">No non-zero cron exits in the visible history.</td></tr>'}</tbody>
        </table>
      </section>

      <section class=\"span-12\">
        <h2>Promotion History</h2>
        <table>
          <thead><tr><th>Deployed At</th><th>Skill</th><th>Score</th><th>Previous</th><th>Source</th></tr></thead>
          <tbody>{promotion_rows or '<tr><td colspan="5" class="subtle">No promotions recorded yet.</td></tr>'}</tbody>
        </table>
      </section>
    </div>
  </main>
</body>
</html>"""


def _cache_state(report: DailyStatusReport) -> str:
    if not report.cache_exists:
        return "missing"
    if report.cache_age_hours is None:
        return "unknown age"
    if report.cache_age_hours > CACHE_MAX_AGE_HOURS:
        return "stale"
    if report.cache_age_hours > CACHE_STALE_WARN_HOURS:
        return "aging"
    return "healthy"


def _cache_detail(report: DailyStatusReport) -> str:
    if not report.cache_exists:
        return "No cache file found."
    if report.cache_age_hours is None:
        return f"{report.videos_fetched} videos, timestamp unavailable."
    return f"{report.cache_age_hours:.1f}h old across {report.videos_fetched} videos."


def _severity_class(label: str) -> str:
    if label == "healthy":
        return "ok"
    if label in {"aging", "unknown age"}:
        return "warn"
    return "bad"


def _breakdown_label(breakdown: dict[str, int]) -> str:
    if not breakdown:
        return "No reactions yet."
    return " · ".join(f"{name} {count}" for name, count in sorted(breakdown.items()))


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    return value.replace("T", " ").replace("+00:00", " UTC")


def _render_delivery(record: DeliveryRecord) -> str:
    picks = record.picks or []
    pick_list = "".join(
        f'<div class="pick"><strong>{escape(pick.title)}</strong><div class="mini">{escape(pick.channel)} · {pick.duration_minutes}m · {escape(pick.video_id)}</div><div>{escape(pick.why_watch)}</div></div>'
        for pick in picks
    )
    if not pick_list:
        pick_list = "".join(
            f'<div class="pick"><strong>{escape(video_id)}</strong></div>'
            for video_id in record.selected_video_ids
        )
    return (
        '<div class="delivery">'
        f'<div class="delivery-head"><strong>{escape(record.skill_name)}</strong>'
        f'<span class="delivery-meta">{escape(_format_timestamp(record.delivered_at))}</span></div>'
        f'<div class="mini">strategy {escape(record.strategy or "—")} · message ids {escape(", ".join(str(i) for i in record.telegram_message_ids) or "—")}</div>'
        f'<div class="pick-list">{pick_list}</div>'
        '</div>'
    )


def _render_trend(trend: ReactionTrendPoint, max_reactions: int) -> str:
    scale = max(max_reactions, 1)
    pos = int((trend.positive / scale) * 100) if trend.positive else 0
    neg = int((trend.negative / scale) * 100) if trend.negative else 0
    other = int((trend.other / scale) * 100) if trend.other else 0
    return (
        '<tr>'
        f'<td>{escape(trend.date)}</td>'
        '<td>'
        f'<div class="mini">👍 {trend.positive} · 👎 {trend.negative}'
        + (f' · other {trend.other}' if trend.other else '')
        + '</div>'
        f'<div class="trendbar"><span class="pos" style="width:{pos}%"></span><span class="neg" style="width:{neg}%"></span><span class="other" style="width:{other}%"></span></div>'
        '</td>'
        f'<td>{trend.total}</td>'
        '</tr>'
    )


def _render_status_row(report: DailyStatusReport) -> str:
    cache = _cache_state(report)
    return (
        '<tr>'
        f'<td>{escape(report.date)}</td>'
        f'<td>{escape(cache)} · {escape(_cache_detail(report))}</td>'
        f'<td>{"sent" if report.digest_sent else "missed"}</td>'
        f'<td>{report.reactions_captured}</td>'
        f'<td>{len(report.failures)}</td>'
        '</tr>'
    )


def _render_leaderboard_row(row: dict[str, Any]) -> str:
    score = float(row["total_score"]) if row.get("total_score") is not None else 0.0
    width = max(1, min(int((score / 10.0) * 100), 100))
    scored_with = "LLM" if row.get("use_llm_judging") else "algorithmic only"
    return (
        '<tr>'
        f'<td>{row["rank"]}</td>'
        f'<td><strong>{escape(str(row.get("skill_name") or row.get("skill_id")))}</strong><div class="mini">{escape(str(row.get("skill_id")))}</div></td>'
        f'<td>{escape(str(row.get("source_type") or "—"))}<div class="mini">{escape(str(row.get("strategy") or "—"))}</div></td>'
        f'<td>{score:.4f}<div class="scorebar"><span style="width:{width}%"></span></div></td>'
        f'<td>{escape(scored_with)}</td>'
        f'<td>{escape(_format_timestamp(row.get("archived_at")))}</td>'
        '</tr>'
    )


def _render_failure(failure: FailureEvent) -> str:
    return (
        '<tr>'
        f'<td>{escape(failure.date)}</td>'
        f'<td>{escape(failure.job)}</td>'
        f'<td>{failure.exit_code}</td>'
        '</tr>'
    )


def _render_promotion(record: DeploymentRecord) -> str:
    previous = escape(record.previous_skill_id or "—")
    if record.previous_score is not None:
        previous += f" ({record.previous_score:.4f})"
    return (
        '<tr>'
        f'<td>{escape(_format_timestamp(record.deployed_at))}</td>'
        f'<td><strong>{escape(record.deployed_skill_id)}</strong></td>'
        f'<td>{record.deployed_score:.4f}</td>'
        f'<td>{previous}</td>'
        f'<td>{escape(record.source_skill_path)}</td>'
        '</tr>'
    )


def _render_current_deployment(record: DeploymentRecord | None) -> str:
    if record is None:
        return '<p class="subtle">No deployment metadata recorded yet.</p>'
    previous = escape(record.previous_skill_id or "—")
    if record.previous_score is not None:
        previous += f" at {record.previous_score:.4f}"
    return (
        f'<p><strong>{escape(record.deployed_skill_id)}</strong> at {record.deployed_score:.4f}</p>'
        f'<p class="mini">Deployed {escape(_format_timestamp(record.deployed_at))}</p>'
        f'<p class="mini">Source {escape(record.source_skill_path)}</p>'
        f'<p class="mini">Previous {previous}</p>'
    )


class DashboardRequestHandler(BaseHTTPRequestHandler):
    builder: DashboardDataBuilder

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        snapshot = self.builder.build()
        if route == "/api/dashboard.json":
            self._send_json(snapshot.to_dict())
            return
        if route not in {"/", "/index.html"}:
            self.send_error(404, "Not found")
            return
        self._send_html(render_dashboard_html(snapshot))

    def log_message(self, _format: str, *args: object) -> None:
        return

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    cache_path: str = _DEFAULT_CACHE_PATH,
) -> None:
    builder = DashboardDataBuilder(cache_path=cache_path)
    handler = type("EvoClawDashboardHandler", (DashboardRequestHandler,), {"builder": builder})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"EvoClaw dashboard running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the EvoClaw local dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on.")
    parser.add_argument("--cache", default=_DEFAULT_CACHE_PATH, help="Path to the active cache JSON.")
    args = parser.parse_args()
    serve_dashboard(host=args.host, port=args.port, cache_path=args.cache)


if __name__ == "__main__":
    main()
