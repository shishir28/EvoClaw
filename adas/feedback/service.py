"""
Step 7 feedback ingestion service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

_log = logging.getLogger(__name__)

try:
    from ..evaluation.models import FeedbackEntry, FeedbackPick, FeedbackVideoSnapshot, VideoRecord
    from .store import FeedbackStore
except ImportError:
    from evaluation.models import FeedbackEntry, FeedbackPick, FeedbackVideoSnapshot, VideoRecord
    from feedback.store import FeedbackStore


VALID_REACTIONS: frozenset[str] = frozenset({
    "up", "thumbs_up", "like", "liked", "positive", "👍",
    "down", "thumbs_down", "dislike", "disliked", "negative", "👎",
})


@dataclass(frozen=True, slots=True)
class ManualFeedbackPick:
    """One manually supplied feedback reaction before cache validation."""

    video_id: str
    reaction: str | None


class FeedbackService:
    """Validate manual feedback and persist it with reusable video snapshots."""

    def __init__(self, store: FeedbackStore | None = None) -> None:
        """Create the service with an injectable feedback store."""
        self._store = store or FeedbackStore()

    def append_feedback(
        self,
        date: str,
        picks: list[ManualFeedbackPick],
        available_videos: list[VideoRecord],
        skill_version: str | None = None,
        feedback_path: str | None = None,
    ) -> FeedbackEntry:
        """Validate picks, attach snapshots, and append one feedback entry."""
        self._validate_request(date, picks)
        videos_by_id = {video.video_id: video for video in available_videos}
        feedback_picks = self._build_feedback_picks(
            picks=picks,
            videos_by_id=videos_by_id,
            skill_version=skill_version,
        )

        entry = FeedbackEntry(date=date, picks=feedback_picks)
        history = self._store.load_history(feedback_path)
        history.append(entry)
        self._store.save_history(history, feedback_path)
        _log.info("feedback entry appended: date=%s picks=%d", date, len(feedback_picks))
        return entry

    def _validate_request(self, date: str, picks: list[ManualFeedbackPick]) -> None:
        """Validate request-level fields before per-pick processing."""
        if not date.strip():
            raise ValueError("Feedback date must not be empty.")
        if not picks:
            raise ValueError("At least one feedback pick is required.")

        duplicate_ids = self._duplicate_ids([pick.video_id for pick in picks])
        if duplicate_ids:
            raise ValueError(
                "Duplicate feedback video IDs are not allowed: " + ", ".join(sorted(duplicate_ids))
            )

    def _build_feedback_picks(
        self,
        picks: list[ManualFeedbackPick],
        videos_by_id: dict[str, VideoRecord],
        skill_version: str | None,
    ) -> list[FeedbackPick]:
        """Convert validated manual picks into stored feedback pick DTOs."""
        feedback_picks: list[FeedbackPick] = []
        for pick in picks:
            self._validate_pick(pick, videos_by_id)
            feedback_picks.append(
                FeedbackPick(
                    video_id=pick.video_id,
                    reaction=pick.reaction,
                    skill_version=skill_version,
                    snapshot=FeedbackVideoSnapshot.from_video(videos_by_id[pick.video_id]),
                )
            )
        return feedback_picks

    @staticmethod
    def _validate_pick(
        pick: ManualFeedbackPick,
        videos_by_id: dict[str, VideoRecord],
    ) -> None:
        """Validate one feedback pick against available videos and reactions."""
        if not pick.video_id.strip():
            raise ValueError("Feedback video_id must not be empty.")
        if pick.video_id not in videos_by_id:
            raise ValueError(f"Feedback video_id not found in available videos: {pick.video_id}")
        if pick.reaction is not None and pick.reaction not in VALID_REACTIONS:
            raise ValueError(
                f"Invalid reaction '{pick.reaction}' for video '{pick.video_id}'. "
                f"Valid values: {sorted(r for r in VALID_REACTIONS if r.isascii())} or None."
            )

    @staticmethod
    def _duplicate_ids(video_ids: list[str]) -> set[str]:
        """Return all duplicate IDs while preserving simple validation logic."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for video_id in video_ids:
            if video_id in seen:
                duplicates.add(video_id)
            seen.add(video_id)
        return duplicates
