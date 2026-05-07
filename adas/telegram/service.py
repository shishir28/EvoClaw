"""Production digest orchestration for Step 11 Telegram delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

try:
    from ..config import DELIVERY_LOG, FEEDBACK_FILE, SKILL_PRODUCTION
    from ..evaluation.models import EvaluationRequest, SkillDocument, VideoRecord
    from ..evaluation.service import Evaluator
    from .delivery_log import DeliveryLogStore
    from .formatter import TelegramDigestFormatter
    from .models import DeliveryRecord, DigestDeliveryResult, TelegramDigestPick
    from .sender import TelegramSender
except ImportError:
    from config import DELIVERY_LOG, FEEDBACK_FILE, SKILL_PRODUCTION
    from evaluation.models import EvaluationRequest, SkillDocument, VideoRecord
    from evaluation.service import Evaluator
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


@dataclass(slots=True)
class ProductionDigestService:
    """Execute the production skill, format a digest, and optionally send it."""

    evaluator: SelectionEvaluator | None = None
    formatter: TelegramDigestFormatter | None = None
    sender: DigestSender | None = None
    delivery_log_store: DeliveryLogStore | None = None
    delivered_at_factory: Callable[[], str] | None = None

    def __post_init__(self) -> None:
        if self.evaluator is None:
            self.evaluator = Evaluator()
        if self.formatter is None:
            self.formatter = TelegramDigestFormatter()
        if self.delivered_at_factory is None:
            self.delivered_at_factory = lambda: datetime.now(timezone.utc).isoformat()

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
        selected_video_ids, execution_notes = self.evaluator.select_video_ids(request)
        if len(selected_video_ids) != 3:
            raise ValueError(
                f"Production digest requires exactly 3 selected videos, got {len(selected_video_ids)}."
            )
        videos = self.evaluator.resolve_selected_videos(request, selected_video_ids)
        picks = self.formatter.build_picks(videos)
        message_text = self.formatter.format_digest(picks)

        receipt = None
        dry_run = not send
        if send:
            sender = self.sender or TelegramSender()
            receipt = sender.send_message(message_text)

        delivery_store = self._resolve_delivery_log_store(skill_path, delivery_log_path)
        record = DeliveryRecord(
            delivered_at=self.delivered_at_factory(),
            dry_run=dry_run,
            skill_name=request.skill.name or Path(skill_path).stem,
            skill_version=request.skill.version,
            strategy=request.skill.strategy,
            production_skill_path=skill_path,
            cache_path=request.cache_path,
            feedback_path=request.feedback_path,
            telegram_chat_id=self._telegram_chat_id(send, receipt),
            telegram_message_id=receipt.message_id if receipt is not None else None,
            selected_video_ids=list(selected_video_ids),
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
            picks=record.picks,
            execution_notes=record.execution_notes,
            message_text=record.message_text,
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
