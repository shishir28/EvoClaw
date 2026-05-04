"""
Tests for Step 7 feedback persistence and append flow.
"""

from __future__ import annotations

import json

import pytest

from evaluation.models import FeedbackEntry, FeedbackPick
from feedback.service import FeedbackService, ManualFeedbackPick
from feedback.store import FeedbackStore
from builders import video


class TestFeedbackStore:
    def test_load_history_reads_history_wrapper_and_snapshots(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        feedback_file.write_text(
            json.dumps(
                {
                    "history": [
                        {
                            "date": "2026-05-04",
                            "picks": [
                                {
                                    "video_id": "v1",
                                    "reaction": "up",
                                    "skill_version": "skill_003",
                                    "snapshot": {
                                        "title": "AI startup guide",
                                        "channel": "Tech",
                                        "channel_id": "ch1",
                                        "published_at": "2026-05-03T00:00:00Z",
                                        "description": "desc",
                                        "query_matched": "AI startup 2026",
                                        "duration_seconds": 600,
                                        "tags": ["ai"],
                                    },
                                }
                            ],
                        }
                    ]
                }
            )
        )

        history = FeedbackStore().load_history(str(feedback_file))

        assert len(history) == 1
        assert history[0].picks[0].snapshot is not None
        assert history[0].picks[0].snapshot.channel_id == "ch1"

    def test_save_history_writes_history_wrapper(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        history = [
            FeedbackEntry(
                date="2026-05-04",
                picks=[FeedbackPick(video_id="v1", reaction="up")],
            )
        ]

        FeedbackStore().save_history(history, str(feedback_file))

        payload = json.loads(feedback_file.read_text())
        assert payload["history"][0]["date"] == "2026-05-04"
        assert payload["history"][0]["picks"][0]["video_id"] == "v1"


class TestFeedbackService:
    def test_append_feedback_persists_snapshots_for_available_videos(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        available_videos = [
            video()
            .with_id("v1")
            .with_title("AI startup tactics")
            .with_channel("Founders", "ch1")
            .build()
        ]

        entry = FeedbackService().append_feedback(
            date="2026-05-04",
            picks=[ManualFeedbackPick(video_id="v1", reaction="up")],
            available_videos=available_videos,
            skill_version="skill_003",
            feedback_path=str(feedback_file),
        )

        assert entry.picks[0].snapshot is not None
        payload = json.loads(feedback_file.read_text())
        assert payload["history"][0]["picks"][0]["skill_version"] == "skill_003"
        assert payload["history"][0]["picks"][0]["snapshot"]["channel_id"] == "ch1"

    def test_append_feedback_rejects_unknown_video_ids(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"

        with pytest.raises(ValueError, match="Feedback video_id not found"):
            FeedbackService().append_feedback(
                date="2026-05-04",
                picks=[ManualFeedbackPick(video_id="missing", reaction="up")],
                available_videos=[video().with_id("v1").build()],
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_rejects_duplicate_ids(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        available_videos = [video().with_id("v1").build()]

        with pytest.raises(ValueError, match="Duplicate feedback video IDs"):
            FeedbackService().append_feedback(
                date="2026-05-04",
                picks=[
                    ManualFeedbackPick(video_id="v1", reaction="up"),
                    ManualFeedbackPick(video_id="v1", reaction="down"),
                ],
                available_videos=available_videos,
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_rejects_empty_date(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="date must not be empty"):
            FeedbackService().append_feedback(
                date="   ",
                picks=[ManualFeedbackPick(video_id="v1", reaction="up")],
                available_videos=[video().with_id("v1").build()],
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_rejects_empty_picks_list(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="At least one feedback pick"):
            FeedbackService().append_feedback(
                date="2026-05-04",
                picks=[],
                available_videos=[video().with_id("v1").build()],
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_rejects_empty_video_id(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="video_id must not be empty"):
            FeedbackService().append_feedback(
                date="2026-05-04",
                picks=[ManualFeedbackPick(video_id="  ", reaction="up")],
                available_videos=[video().with_id("v1").build()],
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_rejects_invalid_reaction_string(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        with pytest.raises(ValueError, match="Invalid reaction"):
            FeedbackService().append_feedback(
                date="2026-05-04",
                picks=[ManualFeedbackPick(video_id="v1", reaction="thumbs up")],
                available_videos=[video().with_id("v1").build()],
                feedback_path=str(feedback_file),
            )

    def test_append_feedback_accepts_none_reaction(self, tmp_path):
        feedback_file = tmp_path / "feedback.json"
        entry = FeedbackService().append_feedback(
            date="2026-05-04",
            picks=[ManualFeedbackPick(video_id="v1", reaction=None)],
            available_videos=[video().with_id("v1").build()],
            feedback_path=str(feedback_file),
        )
        assert entry.picks[0].reaction is None

    @pytest.mark.parametrize("reaction", ["up", "down", "👍", "👎", "like", "dislike"])
    def test_append_feedback_accepts_all_valid_reactions(self, tmp_path, reaction):
        feedback_file = tmp_path / "feedback.json"
        entry = FeedbackService().append_feedback(
            date="2026-05-04",
            picks=[ManualFeedbackPick(video_id="v1", reaction=reaction)],
            available_videos=[video().with_id("v1").build()],
            feedback_path=str(feedback_file),
        )
        assert entry.picks[0].reaction == reaction
