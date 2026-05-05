"""Tests for Step 10 production skill promotion."""

from __future__ import annotations

import json

import pytest

from adas.archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
from adas.archive_runtime.store import ArchiveStore
from adas.deployment.promoter import (
    DeploymentRecord,
    DeploymentRecordStore,
    SkillPromoter,
)


def _entry(skill_id: str, score: float) -> ArchiveIndexEntry:
    return ArchiveIndexEntry(
        skill_id=skill_id,
        skill_name="winner",
        source_type="meta-agent",
        archive_key=f"meta-agent:{skill_id}",
        archive_path=skill_id,
        archived_at="2026-05-05T00:00:00+00:00",
        origin_skill_path=f"/tmp/{skill_id}.md",
        status="scored",
        total_score=score,
        strategy="recency",
    )


def _write_archive(
    archive_dir,
    best_skill_id: str | None = "skill_001",
    score: float = 8.0,
    skill_text: str = "winner skill",
) -> None:
    if best_skill_id:
        skill_dir = archive_dir / best_skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill_text)
        index = ArchiveIndex(
            best_skill_id=best_skill_id,
            best_score=score,
            skills=[_entry(best_skill_id, score)],
        )
    else:
        index = ArchiveIndex()
    ArchiveStore(str(archive_dir)).save_index(index)


class TestSkillPromoter:
    def test_promotes_archive_best_skill_to_production(self, tmp_path):
        archive_dir = tmp_path / "archive"
        production_skill = tmp_path / "skills" / "youtube-curator" / "SKILL.md"
        _write_archive(archive_dir, skill_text="promoted skill")

        promoter = SkillPromoter(
            archive_dir=str(archive_dir),
            production_skill_path=str(production_skill),
            deployed_at_factory=lambda: "2026-05-05T01:00:00+00:00",
        )

        result = promoter.promote_best_skill()

        assert result.promoted is True
        assert result.skill_id == "skill_001"
        assert production_skill.read_text() == "promoted skill"

        metadata = json.loads((production_skill.parent / "deployment.json").read_text())
        assert metadata["deployed_skill_id"] == "skill_001"
        assert metadata["deployed_score"] == 8.0
        assert metadata["deployed_at"] == "2026-05-05T01:00:00+00:00"

    def test_skips_when_archive_has_no_best_skill(self, tmp_path):
        archive_dir = tmp_path / "archive"
        production_skill = tmp_path / "SKILL.md"
        production_skill.write_text("current skill")
        _write_archive(archive_dir, best_skill_id=None)

        promoter = SkillPromoter(
            archive_dir=str(archive_dir),
            production_skill_path=str(production_skill),
        )

        result = promoter.promote_best_skill()

        assert result.promoted is False
        assert result.status == "skipped"
        assert "does not contain" in result.reason
        assert production_skill.read_text() == "current skill"

    def test_skips_when_current_deployment_score_is_equal_or_higher(self, tmp_path):
        archive_dir = tmp_path / "archive"
        production_skill = tmp_path / "SKILL.md"
        deployment_store = DeploymentRecordStore(tmp_path / "deployment.json")
        production_skill.write_text("current skill")
        _write_archive(archive_dir, score=8.0, skill_text="new skill")
        deployment_store.save(
            DeploymentRecord(
                deployed_skill_id="skill_000",
                deployed_score=8.0,
                deployed_at="2026-05-04T00:00:00+00:00",
                source_skill_path="/tmp/old/SKILL.md",
                production_skill_path=str(production_skill),
            )
        )

        promoter = SkillPromoter(
            archive_dir=str(archive_dir),
            production_skill_path=str(production_skill),
            deployment_store=deployment_store,
        )

        result = promoter.promote_best_skill()

        assert result.promoted is False
        assert result.previous_skill_id == "skill_000"
        assert result.previous_score == 8.0
        assert production_skill.read_text() == "current skill"

    def test_promotes_when_archive_score_beats_current_deployment(self, tmp_path):
        archive_dir = tmp_path / "archive"
        production_skill = tmp_path / "SKILL.md"
        deployment_store = DeploymentRecordStore(tmp_path / "deployment.json")
        _write_archive(archive_dir, score=8.5, skill_text="better skill")
        deployment_store.save(
            DeploymentRecord(
                deployed_skill_id="skill_000",
                deployed_score=8.0,
                deployed_at="2026-05-04T00:00:00+00:00",
                source_skill_path="/tmp/old/SKILL.md",
                production_skill_path=str(production_skill),
            )
        )

        promoter = SkillPromoter(
            archive_dir=str(archive_dir),
            production_skill_path=str(production_skill),
            deployment_store=deployment_store,
            deployed_at_factory=lambda: "2026-05-05T01:00:00+00:00",
        )

        result = promoter.promote_best_skill()

        assert result.promoted is True
        assert result.previous_skill_id == "skill_000"
        assert result.previous_score == 8.0
        assert production_skill.read_text() == "better skill"

        record = deployment_store.load()
        assert record is not None
        assert record.deployed_skill_id == "skill_001"
        assert record.deployed_score == 8.5
        assert record.previous_skill_id == "skill_000"

    def test_missing_archived_skill_file_raises(self, tmp_path):
        archive_dir = tmp_path / "archive"
        index = ArchiveIndex(
            best_skill_id="skill_404",
            best_score=9.0,
            skills=[_entry("skill_404", 9.0)],
        )
        ArchiveStore(str(archive_dir)).save_index(index)
        promoter = SkillPromoter(archive_dir=str(archive_dir))

        with pytest.raises(FileNotFoundError, match="Archived skill file"):
            promoter.promote_best_skill()

    def test_skips_when_best_skill_id_has_no_matching_skills_entry(self, tmp_path):
        archive_dir = tmp_path / "archive"
        index = ArchiveIndex(
            best_skill_id="skill_ghost",
            best_score=9.0,
            skills=[_entry("skill_001", 9.0)],  # best_skill_id not in skills list
        )
        ArchiveStore(str(archive_dir)).save_index(index)
        promoter = SkillPromoter(archive_dir=str(archive_dir))

        result = promoter.promote_best_skill()

        assert result.promoted is False
        assert result.status == "skipped"

    def test_promotion_result_to_dict_includes_promoted_flag(self, tmp_path):
        archive_dir = tmp_path / "archive"
        production_skill = tmp_path / "skills" / "youtube-curator" / "SKILL.md"
        _write_archive(archive_dir, skill_text="winner")

        promoter = SkillPromoter(
            archive_dir=str(archive_dir),
            production_skill_path=str(production_skill),
            deployed_at_factory=lambda: "2026-05-05T01:00:00+00:00",
        )

        result = promoter.promote_best_skill()
        d = result.to_dict()

        assert "promoted" in d
        assert d["promoted"] is True
        assert d["status"] == "promoted"
        assert d["skill_id"] == "skill_001"
