"""
Orchestration for evaluating multiple baseline skills against one cache.
"""

from __future__ import annotations

from typing import Protocol

try:
    from ..evaluation.models import EvaluationResult
    from .models import BaselineEvaluationRecord
except ImportError:
    from evaluation.models import EvaluationResult
    from baseline.models import BaselineEvaluationRecord


class EvaluatorProtocol(Protocol):
    def score(
        self,
        skill_path: str,
        cache_path: str,
        selected_video_ids: list[str] | None = None,
        feedback_path: str | None = None,
        extra_scores: dict[str, float] | None = None,
        extra_details: dict[str, str] | None = None,
        use_llm_judging: bool = False,
    ) -> EvaluationResult: ...


class BaselineEvaluationRunner:
    def __init__(self, evaluator: EvaluatorProtocol) -> None:
        self._evaluator = evaluator

    def run(
        self,
        skill_paths: list[str],
        cache_path: str,
        feedback_path: str | None = None,
        use_llm_judging: bool = False,
    ) -> list[BaselineEvaluationRecord]:
        records: list[BaselineEvaluationRecord] = []
        for skill_path in skill_paths:
            try:
                result = self._evaluator.score(
                    skill_path=skill_path,
                    cache_path=cache_path,
                    feedback_path=feedback_path,
                    use_llm_judging=use_llm_judging,
                )
            except Exception as exc:
                records.append(BaselineEvaluationRecord(skill_path=skill_path, error=str(exc)))
                continue

            records.append(BaselineEvaluationRecord(skill_path=skill_path, result=result))
        return records
