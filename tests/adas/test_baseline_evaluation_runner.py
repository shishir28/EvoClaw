"""
Tests for baseline Step 5 orchestration.
"""

from __future__ import annotations

from adas.baseline.runner import BaselineEvaluationRunner
from builders import make_scored_result


class _StubEvaluator:
    def __init__(self, results_by_skill: dict[str, object]) -> None:
        self._results_by_skill = results_by_skill
        self.calls: list[dict[str, object]] = []

    def score(
        self,
        skill_path: str,
        cache_path: str,
        selected_video_ids: list[str] | None = None,
        feedback_path: str | None = None,
        extra_scores: dict[str, float] | None = None,
        extra_details: dict[str, str] | None = None,
        use_llm_judging: bool = False,
    ):
        self.calls.append(
            {
                "skill_path": skill_path,
                "cache_path": cache_path,
                "feedback_path": feedback_path,
                "use_llm_judging": use_llm_judging,
            }
        )
        outcome = self._results_by_skill[skill_path]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestBaselineEvaluationRunner:
    def test_runs_all_skill_paths_in_order(self):
        evaluator = _StubEvaluator(
            {
                "a.md": make_scored_result("a", 6.5),
                "b.md": make_scored_result("b", 7.5),
            }
        )
        runner = BaselineEvaluationRunner(evaluator)

        records = runner.run(
            skill_paths=["a.md", "b.md"],
            cache_path="cache.json",
            feedback_path="feedback.json",
            use_llm_judging=True,
        )

        assert [record.skill_path for record in records] == ["a.md", "b.md"]
        assert [call["skill_path"] for call in evaluator.calls] == ["a.md", "b.md"]

    def test_passes_cache_feedback_and_llm_flags_to_evaluator(self):
        evaluator = _StubEvaluator({"a.md": make_scored_result("a", 6.5)})
        runner = BaselineEvaluationRunner(evaluator)

        runner.run(
            skill_paths=["a.md"],
            cache_path="cache.json",
            feedback_path="feedback.json",
            use_llm_judging=True,
        )

        assert evaluator.calls == [
            {
                "skill_path": "a.md",
                "cache_path": "cache.json",
                "feedback_path": "feedback.json",
                "use_llm_judging": True,
            }
        ]

    def test_records_failures_and_continues(self):
        evaluator = _StubEvaluator(
            {
                "a.md": make_scored_result("a", 6.5),
                "broken.md": ValueError("bad skill"),
                "b.md": make_scored_result("b", 7.5),
            }
        )
        runner = BaselineEvaluationRunner(evaluator)

        records = runner.run(
            skill_paths=["a.md", "broken.md", "b.md"],
            cache_path="cache.json",
        )

        assert records[0].succeeded is True
        assert records[1].succeeded is False
        assert records[1].error == "bad skill"
        assert records[2].succeeded is True
