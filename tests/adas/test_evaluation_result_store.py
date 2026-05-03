"""
Tests for Step 5 result persistence.
"""

from __future__ import annotations

import json

from baseline_evaluation_models import BaselineEvaluationRecord
from evaluation_result_store import EvaluationResultStore
from builders import make_result


def _scored_result(skill_name: str, total_score: float):
    result = make_result()
    result.skill_name = skill_name
    result.total_score = total_score
    result.status = "scored"
    return result


class TestEvaluationResultStore:
    def test_writes_one_result_file_per_record(self, tmp_path):
        store = EvaluationResultStore(generated_at_factory=lambda: "2026-05-03T00:00:00+00:00")
        records = [
            BaselineEvaluationRecord(
                skill_path="adas/baselines/baseline_recency.md",
                result=_scored_result("recency-first", 6.5),
            ),
            BaselineEvaluationRecord(
                skill_path="adas/baselines/baseline_popular.md",
                error="bad skill",
            ),
        ]

        store.save_run(records, str(tmp_path))

        recency_file = tmp_path / "results" / "baseline_recency.json"
        popular_file = tmp_path / "results" / "baseline_popular.json"
        assert recency_file.exists()
        assert popular_file.exists()

        recency_payload = json.loads(recency_file.read_text())
        popular_payload = json.loads(popular_file.read_text())
        assert recency_payload["status"] == "scored"
        assert popular_payload["status"] == "failed"
        assert popular_payload["error"] == "bad skill"

    def test_summary_ranks_scored_results_descending(self, tmp_path):
        store = EvaluationResultStore(generated_at_factory=lambda: "2026-05-03T00:00:00+00:00")
        records = [
            BaselineEvaluationRecord(
                skill_path="adas/baselines/baseline_recency.md",
                result=_scored_result("recency-first", 6.5),
            ),
            BaselineEvaluationRecord(
                skill_path="adas/baselines/baseline_popular.md",
                result=_scored_result("engagement-velocity", 7.5),
            ),
            BaselineEvaluationRecord(
                skill_path="adas/baselines/baseline_curated.md",
                error="judge unavailable",
            ),
        ]

        summary = store.save_run(records, str(tmp_path))

        assert summary["generated_at"] == "2026-05-03T00:00:00+00:00"
        assert [item["skill_name"] for item in summary["ranking"]] == [
            "engagement-velocity",
            "recency-first",
        ]

        summary_file = tmp_path / "summary.json"
        summary_payload = json.loads(summary_file.read_text())
        assert summary_payload["skills"][2]["status"] == "failed"
        assert summary_payload["skills"][2]["error"] == "judge unavailable"
