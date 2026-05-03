"""
Tests for end-to-end Step 5 orchestration across catalog, runner, and store.
"""

from __future__ import annotations

import pytest

from baseline_comparison import BaselineComparisonService


class _StubCatalog:
    def skill_paths(self) -> list[str]:
        return ["a.md", "b.md", "c.md"]


class _StubRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        skill_paths: list[str],
        cache_path: str,
        feedback_path: str | None = None,
        use_llm_judging: bool = False,
    ) -> list[dict[str, str]]:
        self.calls.append(
            {
                "skill_paths": skill_paths,
                "cache_path": cache_path,
                "feedback_path": feedback_path,
                "use_llm_judging": use_llm_judging,
            }
        )
        return [{"skill_path": path} for path in skill_paths]


class _StubStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def save_run(self, records: list[dict[str, str]], output_dir: str) -> dict[str, object]:
        self.calls.append({"records": records, "output_dir": output_dir})
        return {"ranking": [{"skill_name": "b"}]}


class _StubArchiveService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def archive_records(
        self,
        records: list[dict[str, str]],
        source_type: str,
        context: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "records": records,
                "source_type": source_type,
                "context": context,
            }
        )
        return {"best_skill_id": "skill_001", "best_score": 7.5}


class TestBaselineComparisonService:
    def test_compare_uses_catalog_runner_and_store(self):
        runner = _StubRunner()
        store = _StubStore()
        service = BaselineComparisonService(
            catalog=_StubCatalog(),
            runner=runner,
            store=store,
            default_output_root="/tmp/baseline-results",
        )

        result = service.compare(
            cache_path="adas/test_sets/video_cache_w1.json",
            feedback_path="adas/test_sets/feedback.json",
            use_llm_judging=True,
        )

        expected_cache_path = (
            "/home/shishirmishra/Learnings/EvoClaw/adas/test_sets/video_cache_w1.json"
        )
        expected_feedback_path = (
            "/home/shishirmishra/Learnings/EvoClaw/adas/test_sets/feedback.json"
        )
        assert runner.calls == [
            {
                "skill_paths": ["a.md", "b.md", "c.md"],
                "cache_path": expected_cache_path,
                "feedback_path": expected_feedback_path,
                "use_llm_judging": True,
            }
        ]
        assert store.calls == [
            {
                "records": [{"skill_path": "a.md"}, {"skill_path": "b.md"}, {"skill_path": "c.md"}],
                "output_dir": "/tmp/baseline-results/video_cache_w1",
            }
        ]
        assert result["output_dir"] == "/tmp/baseline-results/video_cache_w1"
        assert result["cache_path"] == expected_cache_path
        assert result["summary"]["ranking"] == [{"skill_name": "b"}]

    def test_compare_honors_explicit_output_dir(self):
        service = BaselineComparisonService(
            catalog=_StubCatalog(),
            runner=_StubRunner(),
            store=_StubStore(),
            default_output_root="/tmp/baseline-results",
        )

        result = service.compare(
            cache_path="adas/test_sets/video_cache_w1.json",
            output_dir="/tmp/custom-output",
        )

        assert result["output_dir"] == "/tmp/custom-output"

    def test_compare_resolves_existing_cache_and_feedback_paths(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        feedback_file = tmp_path / "feedback.json"
        cache_file.write_text("{}")
        feedback_file.write_text("{}")

        runner = _StubRunner()
        service = BaselineComparisonService(
            catalog=_StubCatalog(),
            runner=runner,
            store=_StubStore(),
            default_output_root="/tmp/baseline-results",
        )

        result = service.compare(
            cache_path=str(cache_file),
            feedback_path=str(feedback_file),
        )

        assert runner.calls[0]["cache_path"] == str(cache_file.resolve())
        assert runner.calls[0]["feedback_path"] == str(feedback_file.resolve())
        assert result["cache_path"] == str(cache_file.resolve())

    def test_compare_raises_for_missing_cache_path(self):
        service = BaselineComparisonService(
            catalog=_StubCatalog(),
            runner=_StubRunner(),
            store=_StubStore(),
            default_output_root="/tmp/baseline-results",
        )

        with pytest.raises(
            FileNotFoundError,
            match="Required input file does not exist: missing-cache.json",
        ):
            service.compare(cache_path="missing-cache.json")

    def test_compare_can_archive_records_after_persisting_step5_results(self):
        runner = _StubRunner()
        store = _StubStore()
        archive_service = _StubArchiveService()
        service = BaselineComparisonService(
            catalog=_StubCatalog(),
            runner=runner,
            store=store,
            archive_service=archive_service,
            default_output_root="/tmp/baseline-results",
        )

        result = service.compare(
            cache_path="adas/test_sets/video_cache_w1.json",
            feedback_path="adas/test_sets/feedback.json",
            use_llm_judging=True,
            archive_results=True,
        )

        assert archive_service.calls == [
            {
                "records": [{"skill_path": "a.md"}, {"skill_path": "b.md"}, {"skill_path": "c.md"}],
                "source_type": "baseline",
                "context": {
                    "cache_path": "/home/shishirmishra/Learnings/EvoClaw/adas/test_sets/video_cache_w1.json",
                    "feedback_path": "/home/shishirmishra/Learnings/EvoClaw/adas/test_sets/feedback.json",
                    "use_llm_judging": True,
                },
            }
        ]
        assert result["archive"] == {"best_skill_id": "skill_001", "best_score": 7.5}
