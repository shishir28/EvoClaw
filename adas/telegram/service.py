"""Production digest orchestration for Step 11 Telegram delivery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

_log = logging.getLogger(__name__)

try:
    from ..config import (
        CACHE_MAX_AGE_HOURS,
        CACHE_STALE_WARN_HOURS,
        DELIVERY_LOG,
        FEEDBACK_FILE,
        SKILL_PRODUCTION,
    )
    from ..evaluation.models import EvaluationRequest, SkillDocument, VideoRecord
    from ..evaluation.service import Evaluator
    from ..youtube_fetcher import VideoCacheRepository
    from .delivery_log import DeliveryLogStore
    from .formatter import TelegramDigestFormatter
    from .models import DeliveryRecord, DigestDeliveryResult, TelegramDigestPick
    from .sender import TelegramSender
except ImportError:
    from config import (
        CACHE_MAX_AGE_HOURS,
        CACHE_STALE_WARN_HOURS,
        DELIVERY_LOG,
        FEEDBACK_FILE,
        SKILL_PRODUCTION,
    )
    from evaluation.models import EvaluationRequest, SkillDocument, VideoRecord
    from evaluation.service import Evaluator
    from youtube_fetcher import VideoCacheRepository
    from telegram.delivery_log import DeliveryLogStore
    from telegram.formatter import TelegramDigestFormatter
    from telegram.models import DeliveryRecord, DigestDeliveryResult, TelegramDigestPick
    from telegram.sender import TelegramSender


class DigestSender(Protocol):
    """Small protocol for sending a final digest message."""

    chat_id: str

    def send_message(self, text: str): ...


class SelectionEvaluator(Protocol):
    """Public evaluator surface needed by the delivery service."""

    def load_request(
        self,
        skill_path: str,
        cache_path: str,
        feedback_path: str | None = FEEDBACK_FILE,
    ) -> EvaluationRequest: ...

    def select_video_ids(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str] | None = None,
    ) -> tuple[list[str], list[str]]: ...

    def resolve_selected_videos(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str],
    ) -> list[VideoRecord]: ...


class StaleCacheError(RuntimeError):
    """Raised when the candidate cache is too old to deliver a trustworthy digest."""


@dataclass(slots=True)
class CacheFreshnessGate:
    """Decide whether a cache is fresh enough to deliver, and how to flag staleness.

    A healthy cache is refreshed daily, so age is the signal that an upstream
    refresh stalled (the fetcher keeps the last-good cache rather than clobbering
    it). Moderately stale caches still ship with a delivery note; severely stale
    caches abort the digest so we never quietly send day-old picks.
    """

    cache_repository: VideoCacheRepository | None = None
    stale_warn_hours: float = CACHE_STALE_WARN_HOURS
    max_age_hours: float = CACHE_MAX_AGE_HOURS
    now_factory: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if self.cache_repository is None:
            self.cache_repository = VideoCacheRepository()
        if self.now_factory is None:
            self.now_factory = lambda: datetime.now(timezone.utc)

    def evaluate(self, cache_path: str) -> list[str]:
        """Return delivery notes for a cache, raising StaleCacheError when too old."""
        meta = self.cache_repository.load_metadata(cache_path, now=self.now_factory())

        if meta.age_hours is None:
            return [
                "Cache freshness unknown: missing or unreadable 'fetched_at' timestamp; "
                "delivering on a best-effort basis."
            ]

        if meta.age_hours > self.max_age_hours:
            raise StaleCacheError(
                f"Candidate cache at {meta.path} is {meta.age_hours:.1f}h old "
                f"(max {self.max_age_hours:.0f}h). Last successful fetch: "
                f"{meta.fetched_at.isoformat()}. Refusing to deliver a stale digest — "
                f"the YouTube refresh has likely been failing."
            )

        if meta.age_hours > self.stale_warn_hours:
            return [
                f"⚠️ Cache is {meta.age_hours:.1f}h old (fetched {meta.fetched_at.isoformat()}); "
                f"the YouTube refresh may have failed. Picks drawn from the last-good cache."
            ]

        return []


@dataclass(slots=True)
class ProductionDigestService:
    """Execute the production skill, format a digest, and optionally send it."""

    evaluator: SelectionEvaluator | None = None
    formatter: TelegramDigestFormatter | None = None
    sender: DigestSender | None = None
    delivery_log_store: DeliveryLogStore | None = None
    delivered_at_factory: Callable[[], str] | None = None
    freshness_gate: CacheFreshnessGate | None = None

    def __post_init__(self) -> None:
        if self.evaluator is None:
            self.evaluator = Evaluator()
        if self.formatter is None:
            self.formatter = TelegramDigestFormatter()
        if self.delivered_at_factory is None:
            self.delivered_at_factory = lambda: datetime.now(timezone.utc).isoformat()
        if self.freshness_gate is None:
            self.freshness_gate = CacheFreshnessGate()

    def deliver(
        self,
        cache_path: str,
        production_skill_path: str = SKILL_PRODUCTION,
        feedback_path: str | None = FEEDBACK_FILE,
        delivery_log_path: str | None = None,
        send: bool = False,
    ) -> DigestDeliveryResult:
        skill_path = str(Path(production_skill_path))
        request = self.evaluator.load_request(
            skill_path=skill_path,
            cache_path=cache_path,
            feedback_path=feedback_path,
        )
        # Gate on cache freshness before doing any work: too-stale raises here.
        freshness_notes = self.freshness_gate.evaluate(request.cache_path)
        delivery_store = self._resolve_delivery_log_store(skill_path, delivery_log_path)
        previously_delivered_ids = self._previously_delivered_video_ids(delivery_store)
        request = self._exclude_previously_delivered_videos(
            request,
            previously_delivered_ids,
        )
        selected_video_ids, execution_notes = self.evaluator.select_video_ids(request)
        if previously_delivered_ids:
            execution_notes = [
                f"Excluded {len(previously_delivered_ids)} previously delivered video(s).",
                *execution_notes,
            ]
        if freshness_notes:
            execution_notes = [*freshness_notes, *execution_notes]
        if not selected_video_ids:
            raise ValueError("Production digest requires at least 1 selected video.")
        if len(selected_video_ids) > 3:
            execution_notes.append(
                f"Production strategy returned {len(selected_video_ids)} video(s); capping digest at 3 picks."
            )
            selected_video_ids = selected_video_ids[:3]
        elif len(selected_video_ids) < 3:
            execution_notes.append(
                f"Production strategy returned {len(selected_video_ids)} video(s); sending a short digest."
            )
        videos = self.evaluator.resolve_selected_videos(request, selected_video_ids)
        picks = self.formatter.build_picks(videos)
        message_text = self.formatter.format_digest(picks)

        receipts = []
        dry_run = not send
        if send:
            sender = self.sender or TelegramSender()
            _log.info(
                "sending per-video digest to Telegram (skill=%s, videos=%s)",
                request.skill.name,
                selected_video_ids,
            )
            for pick in picks:
                receipts.append(sender.send_message(self.formatter.format_pick_message(pick)))
            _log.info(
                "digest sent: message_ids=%s",
                [receipt.message_id for receipt in receipts],
            )
        else:
            _log.info("dry-run: skipping Telegram send (skill=%s)", request.skill.name)

        first_receipt = receipts[0] if receipts else None
        telegram_message_ids = [receipt.message_id for receipt in receipts]
        pick_message_ids = {
            pick.video_id: receipt.message_id
            for pick, receipt in zip(picks, receipts, strict=True)
        } if receipts else {}

        record = DeliveryRecord(
            delivered_at=self.delivered_at_factory(),
            dry_run=dry_run,
            skill_name=request.skill.name or Path(skill_path).stem,
            skill_version=request.skill.version,
            strategy=request.skill.strategy,
            production_skill_path=skill_path,
            cache_path=request.cache_path,
            feedback_path=request.feedback_path,
            telegram_chat_id=self._telegram_chat_id(send, first_receipt),
            telegram_message_id=first_receipt.message_id if first_receipt is not None else None,
            selected_video_ids=list(selected_video_ids),
            telegram_message_ids=telegram_message_ids,
            pick_message_ids=pick_message_ids,
            picks=list(picks),
            execution_notes=list(execution_notes),
            message_text=message_text,
        )
        delivery_store.append(record)

        return DigestDeliveryResult(
            status="sent" if send else "dry_run",
            dry_run=dry_run,
            skill_name=record.skill_name,
            skill_version=record.skill_version,
            strategy=record.strategy,
            production_skill_path=record.production_skill_path,
            cache_path=record.cache_path,
            feedback_path=record.feedback_path,
            delivery_log_path=str(delivery_store.path),
            telegram_chat_id=record.telegram_chat_id,
            telegram_message_id=record.telegram_message_id,
            selected_video_ids=record.selected_video_ids,
            telegram_message_ids=record.telegram_message_ids,
            pick_message_ids=record.pick_message_ids,
            picks=record.picks,
            execution_notes=record.execution_notes,
            message_text=record.message_text,
        )

    @staticmethod
    def _previously_delivered_video_ids(
        delivery_store: DeliveryLogStore,
    ) -> set[str]:
        """Return video IDs from live sends so production does not repeat picks."""
        return {
            video_id
            for record in delivery_store.load_history()
            if not record.dry_run
            for video_id in record.selected_video_ids
        }

    @staticmethod
    def _exclude_previously_delivered_videos(
        request: EvaluationRequest,
        previously_delivered_ids: set[str],
    ) -> EvaluationRequest:
        """Filter already-sent videos before the strategy executor ranks candidates."""
        if not previously_delivered_ids:
            return request
        return replace(
            request,
            videos=[
                video
                for video in request.videos
                if video.video_id not in previously_delivered_ids
            ],
        )

    def _resolve_delivery_log_store(
        self,
        production_skill_path: str,
        delivery_log_path: str | None,
    ) -> DeliveryLogStore:
        if self.delivery_log_store is not None:
            return self.delivery_log_store
        if delivery_log_path:
            return DeliveryLogStore(delivery_log_path)
        return DeliveryLogStore(Path(production_skill_path).with_name("delivery_log.json"))

    def _telegram_chat_id(self, send: bool, receipt) -> str | None:
        if receipt is not None:
            return receipt.chat_id
        if send and self.sender is not None:
            return getattr(self.sender, "chat_id", None)
        return None


def send_digest(
    cache_path: str,
    production_skill_path: str = SKILL_PRODUCTION,
    feedback_path: str | None = FEEDBACK_FILE,
    delivery_log_path: str = DELIVERY_LOG,
    send: bool = False,
) -> DigestDeliveryResult:
    """Convenience entrypoint used by the manual CLI."""
    service = ProductionDigestService()
    return service.deliver(
        cache_path=cache_path,
        production_skill_path=production_skill_path,
        feedback_path=feedback_path,
        delivery_log_path=delivery_log_path,
        send=send,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the production YouTube curator skill and optionally send its Telegram digest.",
    )
    parser.add_argument("--cache", required=True, help="Path to a cached video JSON file")
    parser.add_argument(
        "--skill",
        default=SKILL_PRODUCTION,
        help="Path to the production SKILL.md file",
    )
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        help="Optional path to feedback JSON",
    )
    parser.add_argument(
        "--delivery-log",
        default=DELIVERY_LOG,
        help="Path to the delivery metadata log JSON",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the digest to Telegram. Without this flag the command runs in dry-run mode.",
    )
    args = parser.parse_args()

    result = send_digest(
        cache_path=args.cache,
        production_skill_path=args.skill,
        feedback_path=args.feedback,
        delivery_log_path=args.delivery_log,
        send=args.send,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
