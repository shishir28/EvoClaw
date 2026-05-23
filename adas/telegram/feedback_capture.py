"""Map Telegram reactions on digest messages back to per-video feedback entries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ..config import DELIVERY_LOG, FEEDBACK_FILE
    from ..evaluation.models import VideoRecord
    from ..feedback.service import FeedbackService, ManualFeedbackPick
    from ..utils.paths import write_text_atomic
    from ..youtube_fetcher import VideoCacheRepository
    from .delivery_log import DeliveryLogStore
    from .models import DeliveryRecord
    from .reaction_poller import ReactionUpdate, TelegramReactionPoller
except ImportError:
    from config import DELIVERY_LOG, FEEDBACK_FILE
    from evaluation.models import VideoRecord
    from feedback.service import FeedbackService, ManualFeedbackPick
    from utils.paths import write_text_atomic
    from youtube_fetcher import VideoCacheRepository
    from telegram.delivery_log import DeliveryLogStore
    from telegram.models import DeliveryRecord
    from telegram.reaction_poller import ReactionUpdate, TelegramReactionPoller


# Emoji reactions that map to positive/negative signals.
_POSITIVE_EMOJIS: frozenset[str] = frozenset({"👍", "❤", "🔥", "⭐", "🎉"})
_NEGATIVE_EMOJIS: frozenset[str] = frozenset({"👎", "💔", "🤮"})


def _emoji_to_reaction(emoji: str) -> str | None:
    if emoji in _POSITIVE_EMOJIS:
        return "👍"
    if emoji in _NEGATIVE_EMOJIS:
        return "👎"
    return None


@dataclass(slots=True)
class ReactionCaptureResult:
    """Summary of one poll-and-capture run."""

    updates_processed: int
    feedback_entries_written: int
    skipped_no_match: int
    new_offset: int | None
    messages: list[str] = None  # noqa: RUF009

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "updates_processed": self.updates_processed,
            "feedback_entries_written": self.feedback_entries_written,
            "skipped_no_match": self.skipped_no_match,
            "new_offset": self.new_offset,
            "messages": self.messages,
        }


class ReactionFeedbackCapture:
    """Poll for Telegram reactions and write matching feedback entries."""

    def __init__(
        self,
        poller: TelegramReactionPoller | None = None,
        delivery_log_store: DeliveryLogStore | None = None,
        feedback_service: FeedbackService | None = None,
        cache_repository: VideoCacheRepository | None = None,
    ) -> None:
        self._poller = poller or TelegramReactionPoller()
        self._delivery_log_store = delivery_log_store or DeliveryLogStore(DELIVERY_LOG)
        self._feedback_service = feedback_service or FeedbackService()
        self._cache_repository = cache_repository or VideoCacheRepository()

    def capture(
        self,
        offset_path: str | None = None,
        feedback_path: str | None = None,
    ) -> ReactionCaptureResult:
        """Poll once and write feedback for any reactions that match known deliveries."""
        offset_file = Path(offset_path) if offset_path else self._default_offset_path()
        offset = self._load_offset(offset_file)

        updates = self._poller.poll(offset=offset)
        if not updates:
            return ReactionCaptureResult(
                updates_processed=0,
                feedback_entries_written=0,
                skipped_no_match=0,
                new_offset=offset,
            )

        delivery_map = self._build_delivery_map()
        messages: list[str] = []
        entries_written = 0
        skipped = 0

        for update in updates:
            matched = delivery_map.get(update.message_id)
            if matched is None:
                skipped += 1
                continue

            matched_record, target_video_ids = matched
            reactions = [_emoji_to_reaction(e) for e in update.new_reactions]
            reactions = [r for r in reactions if r is not None]
            if not reactions:
                # Reaction removed or unrecognised emoji — skip silently.
                skipped += 1
                continue

            reaction = reactions[0]
            wrote = self._write_feedback(
                matched_record,
                reaction,
                feedback_path,
                target_video_ids,
            )
            if wrote:
                entries_written += 1
                pick_label = "pick" if len(target_video_ids) == 1 else "picks"
                messages.append(
                    f"message_id={update.message_id}: reaction={reaction} "
                    f"→ {len(target_video_ids)} {pick_label} recorded"
                )
            else:
                skipped += 1

        new_offset = updates[-1].update_id + 1
        self._save_offset(offset_file, new_offset)

        return ReactionCaptureResult(
            updates_processed=len(updates),
            feedback_entries_written=entries_written,
            skipped_no_match=skipped,
            new_offset=new_offset,
            messages=messages,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_delivery_map(self) -> dict[int, tuple[DeliveryRecord, list[str]]]:
        """Build message_id → (delivery, target video IDs) for live deliveries.

        New delivery records store one Telegram message ID per video pick. Older
        records only have a digest-level message ID, so they remain supported as
        whole-digest feedback for historical compatibility.
        """
        records = self._delivery_log_store.load_history()
        delivery_map: dict[int, tuple[DeliveryRecord, list[str]]] = {}
        for record in records:
            if record.dry_run:
                continue
            for video_id, message_id in record.pick_message_ids.items():
                delivery_map[int(message_id)] = (record, [video_id])
            if not record.pick_message_ids and record.telegram_message_id is not None:
                delivery_map[record.telegram_message_id] = (
                    record,
                    list(record.selected_video_ids),
                )
        return delivery_map

    def _write_feedback(
        self,
        record: DeliveryRecord,
        reaction: str,
        feedback_path: str | None,
        target_video_ids: list[str],
    ) -> bool:
        """Load videos from cache and append one feedback entry. Returns True on success."""
        videos = self._load_videos(record)
        if not videos:
            return False

        available_video_ids = {v.video_id for v in videos}
        picks = [
            ManualFeedbackPick(video_id=vid, reaction=reaction)
            for vid in target_video_ids
            if vid in available_video_ids
        ]
        if not picks:
            return False

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._feedback_service.append_feedback(
            date=date,
            picks=picks,
            available_videos=videos,
            skill_version=record.skill_version,
            feedback_path=feedback_path,
        )
        return True

    def _load_videos(self, record: DeliveryRecord) -> list[VideoRecord]:
        """Load VideoRecords for the selected IDs from the record's cache file."""
        cache_path = Path(record.cache_path)
        if not cache_path.exists():
            return []
        try:
            raw_videos = self._cache_repository.load(str(cache_path))
        except Exception:
            return []
        wanted = set(record.selected_video_ids)
        return [
            VideoRecord.from_dict(v)
            for v in raw_videos
            if v.get("video_id") in wanted
        ]

    def _default_offset_path(self) -> Path:
        return Path(DELIVERY_LOG).parent / "reaction_poll_offset.json"

    @staticmethod
    def _load_offset(path: Path) -> int | None:
        if not path.exists():
            return None
        try:
            return int(json.loads(path.read_text()).get("offset"))
        except Exception:
            return None

    @staticmethod
    def _save_offset(path: Path, offset: int) -> None:
        write_text_atomic(path, json.dumps({"offset": offset}, indent=2))
