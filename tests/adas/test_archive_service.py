"""
Tests for Step 6 archive persistence and indexing.
"""

from __future__ import annotations

import json

from adas.archive_runtime.service import ArchiveService
from adas.archive_runtime.store import ArchiveStore
from adas.baseline.models import BaselineEvaluationRecord
from builders import make_scored_result


def _write_skill_file(path, title: str) -> None:
    path.write_text(f"---\nname: {title}\nstrategy: recency\n---\n\n# {title}\n")


class TestArchiveService:
    def test_archive_records_writes_skill_result_meta_and_index(self, tmp_path):
        archive_root = tmp_path / "archive"
        recency_skill = tmp_path / "baseline_recency.md"
        popular_skill = tmp_path / "baseline_popular.md"
        broken_skill = tmp_path / "baseline_broken.md"
        _write_skill_file(recency_skill, "recency-first")
        _write_skill_file(popular_skill, "engagement-velocity")
        _write_skill_file(broken_skill, "broken-baseline")

        service = ArchiveService(
            store=ArchiveStore(str(archive_root)),
            archived_at_factory=lambda: "2026-05-03T00:00:00+00:00",
        )
        records = [
            BaselineEvaluationRecord(
                skill_path=str(recency_skill),
                result=make_scored_result("recency-first", 6.5),
            ),
            BaselineEvaluationRecord(
                skill_path=str(popular_skill),
                result=make_scored_result("engagement-velocity", 7.5),
            ),
            BaselineEvaluationRecord(
                skill_path=str(broken_skill),
                error="bad skill",
            ),
        ]

        index_payload = service.archive_records(
            records=records,
            source_type="baseline",
            context={
                "cache_path": "/tmp/cache.json",
                "feedback_path": "/tmp/feedback.json",
                "use_llm_judging": True,
            },
        )

        assert index_payload["best_skill_id"] == "skill_002"
        assert index_payload["best_score"] == 7.5
        assert [entry["skill_id"] for entry in index_payload["skills"]] == [
            "skill_001",
            "skill_002",
            "skill_003",
        ]

        recency_dir = archive_root / "skill_001"
        popular_dir = archive_root / "skill_002"
        broken_dir = archive_root / "skill_003"
        assert recency_dir.joinpath("SKILL.md").exists()
        assert popular_dir.joinpath("result.json").exists()
        assert broken_dir.joinpath("meta.json").exists()

        recency_payload = json.loads((recency_dir / "result.json").read_text())
        broken_payload = json.loads((broken_dir / "result.json").read_text())
        popular_meta = json.loads((popular_dir / "meta.json").read_text())
        assert recency_payload["result"]["skill_name"] == "recency-first"
        assert broken_payload["status"] == "failed"
        assert broken_payload["error"] == "bad skill"
        assert popular_meta["context"]["use_llm_judging"] is True
        assert popular_meta["archive_path"] == "skill_002"

        index_file_payload = json.loads((archive_root / "index.json").read_text())
        assert index_file_payload["best_skill_id"] == "skill_002"
        assert index_file_payload["skills"][2]["status"] == "failed"

    def test_archive_records_reuses_existing_skill_id_for_same_context(self, tmp_path):
        archive_root = tmp_path / "archive"
        skill_path = tmp_path / "baseline_recency.md"
        _write_skill_file(skill_path, "recency-first")

        service = ArchiveService(
            store=ArchiveStore(str(archive_root)),
            archived_at_factory=lambda: "2026-05-03T00:00:00+00:00",
        )
        context = {
            "cache_path": "/tmp/cache.json",
            "feedback_path": None,
            "use_llm_judging": True,
        }

        first_index = service.archive_records(
            records=[
                BaselineEvaluationRecord(
                    skill_path=str(skill_path),
                    result=make_scored_result("recency-first", 6.5),
                )
            ],
            source_type="baseline",
            context=context,
        )
        second_index = service.archive_records(
            records=[
                BaselineEvaluationRecord(
                    skill_path=str(skill_path),
                    result=make_scored_result("recency-first", 7.0),
                )
            ],
            source_type="baseline",
            context=context,
        )

        assert first_index["skills"][0]["skill_id"] == "skill_001"
        assert second_index["skills"][0]["skill_id"] == "skill_001"
        assert len(second_index["skills"]) == 1
        assert second_index["best_skill_id"] == "skill_001"
        assert second_index["best_score"] == 7.0

        result_payload = json.loads((archive_root / "skill_001" / "result.json").read_text())
        assert result_payload["total_score"] == 7.0
