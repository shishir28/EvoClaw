"""
Step 7 feedback ingestion service.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    video_id: str
    reaction: str | None


class FeedbackService:
    def __init__(self, store: FeedbackStore | None = None) -> None:
        self._store = store or FeedbackStore()

    def append_feedback(
        self,
        date: str,
        picks: list[ManualFeedbackPick],
        available_videos: list[VideoRecord],
        skill_version: str | None = None,
        feedback_path: str | None = None,
    ) -> FeedbackEntry:
        if not date.strip():
            raise ValueError("Feedback date must not be empty.")
        if not picks:
            raise ValueError("At least one feedback pick is required.")

        videos_by_id = {video.video_id: video for video in available_videos}
        duplicate_ids = self._duplicate_ids([pick.video_id for pick in picks])
        if duplicate_ids:
            raise ValueError(
                "Duplicate feedback video IDs are not allowed: " + ", ".join(sorted(duplicate_ids))
            )

        feedback_picks: list[FeedbackPick] = []
        for pick in picks:
            if not pick.video_id.strip():
                raise ValueError("Feedback video_id must not be empty.")
            if pick.video_id not in videos_by_id:
                raise ValueError(f"Feedback video_id not found in available videos: {pick.video_id}")
            if pick.reaction is not None and pick.reaction not in VALID_REACTIONS:
                raise ValueError(
                    f"Invalid reaction '{pick.reaction}' for video '{pick.video_id}'. "
                    f"Valid values: {sorted(r for r in VALID_REACTIONS if r.isascii())} or None."
                )
            feedback_picks.append(
                FeedbackPick(
                    video_id=pick.video_id,
                    reaction=pick.reaction,
                    skill_version=skill_version,
                    snapshot=FeedbackVideoSnapshot.from_video(videos_by_id[pick.video_id]),
                )
            )

        entry = FeedbackEntry(date=date, picks=feedback_picks)
        history = self._store.load_history(feedback_path)
        history.append(entry)
        self._store.save_history(history, feedback_path)
        return entry

    @staticmethod
    def _duplicate_ids(video_ids: list[str]) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for video_id in video_ids:
            if video_id in seen:
                duplicates.add(video_id)
            seen.add(video_id)
        return duplicates
