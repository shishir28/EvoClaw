"""
Manual CLI for appending feedback entries to feedback.json.
"""

from __future__ import annotations

import json

from adas.evaluation.models import VideoRecord
from adas.feedback.service import FeedbackService, ManualFeedbackPick
from adas.youtube_fetcher import VideoCacheRepository


def _parse_pick(raw_pick: str) -> ManualFeedbackPick:
    if "=" not in raw_pick:
        raise ValueError(f"Invalid --pick format '{raw_pick}'. Use video_id=reaction.")
    video_id, reaction = raw_pick.split("=", 1)
    normalized_reaction = reaction.strip()
    return ManualFeedbackPick(
        video_id=video_id.strip(),
        reaction=(normalized_reaction or None),
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Append manual feedback to feedback.json.")
    parser.add_argument("--date", required=True, help="Feedback date, e.g. 2026-05-04")
    parser.add_argument("--cache", required=True, help="Cache JSON used to resolve video snapshots.")
    parser.add_argument(
        "--pick",
        action="append",
        required=True,
        help="Repeatable pick in the form video_id=reaction, where reaction can be up, down, or empty.",
    )
    parser.add_argument("--skill-version", help="Optional archived skill ID or version for this feedback batch.")
    parser.add_argument("--feedback", help="Optional feedback.json path override.")
    args = parser.parse_args()

    available_videos = [
        VideoRecord.from_dict(video)
        for video in VideoCacheRepository().load(args.cache)
    ]
    entry = FeedbackService().append_feedback(
        date=args.date,
        picks=[_parse_pick(raw_pick) for raw_pick in args.pick],
        available_videos=available_videos,
        skill_version=args.skill_version,
        feedback_path=args.feedback,
    )
    print(json.dumps(entry.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
