"""Data models for Telegram digest delivery."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TelegramDigestPick:
    """One formatted pick included in a Telegram digest."""

    rank: int
    video_id: str
    title: str
    channel: str
    url: str
    duration_minutes: int
    age_label: str
    why_watch: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TelegramSendReceipt:
    """Message metadata returned by the Telegram Bot API."""

    chat_id: str
    message_id: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """Persisted metadata for one digest send or dry run."""

    delivered_at: str
    dry_run: bool
    skill_name: str
    skill_version: str | None
    strategy: str | None
    production_skill_path: str
    cache_path: str
    feedback_path: str | None
    telegram_chat_id: str | None
    telegram_message_id: int | None
    selected_video_ids: list[str]
    picks: list[TelegramDigestPick] = field(default_factory=list)
    execution_notes: list[str] = field(default_factory=list)
    message_text: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DeliveryRecord":
        return cls(
            delivered_at=str(payload.get("delivered_at", "")),
            dry_run=bool(payload.get("dry_run", False)),
            skill_name=str(payload.get("skill_name", "")),
            skill_version=(
                str(payload["skill_version"])
                if payload.get("skill_version") is not None
                else None
            ),
            strategy=(
                str(payload["strategy"]) if payload.get("strategy") is not None else None
            ),
            production_skill_path=str(payload.get("production_skill_path", "")),
            cache_path=str(payload.get("cache_path", "")),
            feedback_path=(
                str(payload["feedback_path"])
                if payload.get("feedback_path") is not None
                else None
            ),
            telegram_chat_id=(
                str(payload["telegram_chat_id"])
                if payload.get("telegram_chat_id") is not None
                else None
            ),
            telegram_message_id=(
                int(payload["telegram_message_id"])
                if payload.get("telegram_message_id") is not None
                else None
            ),
            selected_video_ids=[str(video_id) for video_id in payload.get("selected_video_ids", [])],
            picks=[
                TelegramDigestPick(**pick)
                for pick in payload.get("picks", [])
                if isinstance(pick, dict)
            ],
            execution_notes=[str(note) for note in payload.get("execution_notes", [])],
            message_text=str(payload.get("message_text", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "picks": [pick.to_dict() for pick in self.picks],
        }


@dataclass(frozen=True, slots=True)
class DigestDeliveryResult:
    """Public result returned by the production digest service and CLI."""

    status: str
    dry_run: bool
    skill_name: str
    skill_version: str | None
    strategy: str | None
    production_skill_path: str
    cache_path: str
    feedback_path: str | None
    delivery_log_path: str
    telegram_chat_id: str | None
    telegram_message_id: int | None
    selected_video_ids: list[str]
    picks: list[TelegramDigestPick] = field(default_factory=list)
    execution_notes: list[str] = field(default_factory=list)
    message_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "picks": [pick.to_dict() for pick in self.picks],
        }
