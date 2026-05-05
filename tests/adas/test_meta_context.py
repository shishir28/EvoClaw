"""Tests for adas.meta.context."""

from __future__ import annotations

import json

from adas.archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
from adas.evaluation.models import FeedbackEntry, FeedbackPick, FeedbackVideoSnapshot
from adas.meta.context import build_context


def _archive_entry(skill_id: str, skill_name: str, strategy: str, score: float) -> ArchiveIndexEntry:
    return ArchiveIndexEntry(
        skill_id=skill_id,
        skill_name=skill_name,
        source_type="baseline",
        archive_key=f"baseline:{skill_id}",
        archive_path=skill_id,
        archived_at="2026-05-04T00:00:00+00:00",
        origin_skill_path=f"/tmp/{skill_id}.md",
        status="scored",
        total_score=score,
        strategy=strategy,
    )


class _FakeArchiveStore:
    def __init__(self, index: ArchiveIndex) -> None:
        self._index = index

    def load_index(self) -> ArchiveIndex:
        return self._index


class _FakeFeedbackStore:
    def __init__(self, history: list[FeedbackEntry]) -> None:
        self._history = history

    def load_history(self, path: str | None = None) -> list[FeedbackEntry]:
        return self._history


class TestBuildContext:
    def test_cold_start_builds_empty_context(self, tmp_path):
        ctx = build_context(
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            design_goal="first run",
            archive_store=_FakeArchiveStore(ArchiveIndex()),
            feedback_store=_FakeFeedbackStore([]),
        )

        assert json.loads(ctx.archive_index_json)["skills"] == []
        assert json.loads(ctx.archive_skill_summaries_json) == []
        assert ctx.best_skill_md == ""
        assert json.loads(ctx.recent_feedback_summary_json)["recent_picks"] == []
        assert ctx.design_goal == "first run"

    def test_best_skill_and_description_are_loaded(self, tmp_path):
        archive_dir = tmp_path / "archive"
        skill_dir = archive_dir / "skill_007"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: best-skill\n"
            'version: "1.0"\n'
            "strategy: recency\n"
            "description: Best archived skill.\n"
            "author: adas-meta\n"
            "score: null\n"
            "---\n"
            "\n"
            "## Goal\nPick good videos.\n"
        )
        index = ArchiveIndex(
            best_skill_id="skill_007",
            best_score=8.2,
            skills=[_archive_entry("skill_007", "best-skill", "recency", 8.2)],
        )

        ctx = build_context(
            archive_dir=str(archive_dir),
            feedback_path=str(tmp_path / "feedback.json"),
            archive_store=_FakeArchiveStore(index),
            feedback_store=_FakeFeedbackStore([]),
        )

        summaries = json.loads(ctx.archive_skill_summaries_json)
        assert summaries[0]["description"] == "Best archived skill."
        assert "best-skill" in ctx.best_skill_md

    def test_feedback_summary_groups_reactions(self, tmp_path):
        history = [
            FeedbackEntry(
                date="2026-05-04",
                picks=[
                    FeedbackPick(
                        video_id="v1",
                        reaction="up",
                        snapshot=FeedbackVideoSnapshot(
                            title="t1",
                            channel="Liked Channel",
                            channel_id="c1",
                            published_at="2026-05-03T00:00:00Z",
                            description="d1",
                            query_matched="ai founders",
                            duration_seconds=600,
                            tags=["ai"],
                        ),
                    ),
                    FeedbackPick(
                        video_id="v2",
                        reaction="down",
                        snapshot=FeedbackVideoSnapshot(
                            title="t2",
                            channel="Disliked Channel",
                            channel_id="c2",
                            published_at="2026-05-03T00:00:00Z",
                            description="d2",
                            query_matched="generic business",
                            duration_seconds=600,
                            tags=["business"],
                        ),
                    ),
                ],
            )
        ]

        ctx = build_context(
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            archive_store=_FakeArchiveStore(ArchiveIndex()),
            feedback_store=_FakeFeedbackStore(history),
        )

        summary = json.loads(ctx.recent_feedback_summary_json)
        assert summary["liked_channels"] == ["Liked Channel"]
        assert summary["disliked_channels"] == ["Disliked Channel"]
        assert summary["liked_topics"] == ["ai founders"]
        assert summary["disliked_topics"] == ["generic business"]
        assert len(summary["recent_picks"]) == 2
