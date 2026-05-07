"""
Evaluator orchestration for ADAS skill scoring.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

try:
    from ..config import FEEDBACK_FILE, SCORE_WEIGHTS
    from .executor import BaselineSkillExecutor
    from .judge import LLMJudge
    from .loader import EvaluationRequestLoader
    from .models import DimensionScore, EvaluationRequest, EvaluationResult, VideoRecord
    from .scorer import AlgorithmicScorer
except ImportError:
    from config import FEEDBACK_FILE, SCORE_WEIGHTS
    from evaluation.executor import BaselineSkillExecutor
    from evaluation.judge import LLMJudge
    from evaluation.loader import EvaluationRequestLoader
    from evaluation.models import DimensionScore, EvaluationRequest, EvaluationResult, VideoRecord
    from evaluation.scorer import AlgorithmicScorer


class Evaluator:
    def __init__(
        self,
        request_loader: EvaluationRequestLoader | None = None,
        skill_executor: BaselineSkillExecutor | None = None,
        algorithmic_scorer: AlgorithmicScorer | None = None,
        llm_judge: LLMJudge | None = None,
        score_weights: dict[str, float] | None = None,
    ) -> None:
        """Wire up all scoring dependencies, creating default instances when none are injected."""
        self._request_loader = request_loader or EvaluationRequestLoader()
        self._skill_executor = skill_executor or BaselineSkillExecutor()
        self._algorithmic_scorer = algorithmic_scorer or AlgorithmicScorer()
        self._llm_judge = llm_judge
        self._score_weights = score_weights or SCORE_WEIGHTS

    def _get_llm_judge(self) -> LLMJudge:
        if self._llm_judge is None:
            self._llm_judge = LLMJudge()
        return self._llm_judge

    def load_request(
        self,
        skill_path: str,
        cache_path: str,
        feedback_path: str | None = FEEDBACK_FILE,
    ) -> EvaluationRequest:
        """Load and assemble a typed EvaluationRequest from a skill file, video cache, and optional feedback."""
        return self._request_loader.load_request(
            skill_path=skill_path,
            cache_path=cache_path,
            feedback_path=feedback_path,
        )

    def build_result_template(self, request: EvaluationRequest) -> EvaluationResult:
        """Create a blank EvaluationResult shell with all dimension scores initialised to None."""
        dimensions = [
            DimensionScore(name=name, weight=weight, detail="Not scored yet.")
            for name, weight in self._score_weights.items()
        ]
        return EvaluationResult(
            skill_name=request.skill.name or Path(request.skill.path).stem,
            strategy=request.skill.strategy,
            cache_path=request.cache_path,
            video_count=len(request.videos),
            dimensions=dimensions,
            notes=[
                "Supports partial scoring until every dimension has a value.",
                "Weighted aggregation is applied once all dimension scores are assigned.",
            ],
        )

    def resolve_selected_videos(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str],
    ) -> list[VideoRecord]:
        """Validate selected video IDs against the cache and return the matching VideoRecord objects."""
        if not selected_video_ids:
            raise ValueError("selected_video_ids must contain at least one video ID.")
        if len(selected_video_ids) != len(set(selected_video_ids)):
            raise ValueError("selected_video_ids must not contain duplicates.")

        videos_by_id = {video.video_id: video for video in request.videos}
        missing_video_ids = [
            video_id for video_id in selected_video_ids if video_id not in videos_by_id
        ]
        if missing_video_ids:
            raise ValueError(
                "Selected video IDs not found in cache: " + ", ".join(missing_video_ids)
            )
        return [videos_by_id[video_id] for video_id in selected_video_ids]

    def apply_dimension_scores(
        self,
        result: EvaluationResult,
        scores: dict[str, float],
        details: dict[str, str] | None = None,
    ) -> EvaluationResult:
        """Write numeric scores and optional detail strings into the result's DimensionScore objects, validating the 0–10 range."""
        details = details or {}
        dimension_map = result.dimension_map()

        unexpected_dimensions = sorted(set(scores) - set(dimension_map))
        if unexpected_dimensions:
            raise ValueError(
                f"Unknown dimension score(s): {', '.join(unexpected_dimensions)}"
            )
        unexpected_detail_dimensions = sorted(set(details) - set(dimension_map))
        if unexpected_detail_dimensions:
            raise ValueError(
                f"Unknown dimension detail(s): {', '.join(unexpected_detail_dimensions)}"
            )

        for name, detail in details.items():
            dimension_map[name].detail = detail

        for name, score in scores.items():
            if not 0.0 <= score <= 10.0:
                raise ValueError(f"Score for '{name}' must be between 0 and 10.")
            dimension_map[name].score = round(float(score), 4)

        return result

    def aggregate_weighted_score(self, result: EvaluationResult) -> EvaluationResult:
        """Compute the weighted total score across all dimensions and set result status to 'scored'."""
        dimension_map = result.dimension_map()
        expected_dimensions = set(self._score_weights)
        actual_dimensions = set(dimension_map)

        missing_dimensions = sorted(expected_dimensions - actual_dimensions)
        unexpected_dimensions = sorted(actual_dimensions - expected_dimensions)
        if missing_dimensions or unexpected_dimensions:
            problems: list[str] = []
            if missing_dimensions:
                problems.append(f"missing dimensions: {', '.join(missing_dimensions)}")
            if unexpected_dimensions:
                problems.append(
                    f"unexpected dimensions: {', '.join(unexpected_dimensions)}"
                )
            raise ValueError(
                "Cannot aggregate result with mismatched dimensions: " + "; ".join(problems)
            )

        total_weight = sum(dimension.weight for dimension in result.dimensions)
        if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"Dimension weights must sum to 1.0, got {total_weight}.")

        missing_scores = sorted(
            dimension.name for dimension in result.dimensions if dimension.score is None
        )
        if missing_scores:
            raise ValueError(
                "Cannot aggregate weighted score without values for: "
                + ", ".join(missing_scores)
            )

        weighted_total = sum(
            dimension.weight * float(dimension.score)
            for dimension in result.dimensions
        )
        result.total_score = round(weighted_total, 4)
        result.status = "scored"
        return result

    def score_algorithmic_dimensions(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str],
    ) -> EvaluationResult:
        """Run the deterministic freshness, diversity, and alignment scorers and return a partially-scored result."""
        selected_videos = self.resolve_selected_videos(request, selected_video_ids)
        result = self.build_result_template(request)
        result.selected_video_ids = selected_video_ids

        freshness_score, freshness_detail = self._algorithmic_scorer.score_freshness(selected_videos)
        diversity_score, diversity_detail = self._algorithmic_scorer.score_diversity(selected_videos)
        alignment_score, alignment_detail = self._algorithmic_scorer.score_alignment(
            request,
            selected_videos,
        )

        self.apply_dimension_scores(
            result,
            {
                "freshness": freshness_score,
                "diversity": diversity_score,
                "alignment": alignment_score,
            },
            details={
                "freshness": freshness_detail,
                "diversity": diversity_detail,
                "alignment": alignment_detail,
                "relevance": "Pending LLM judge.",
                "substance": "Pending LLM judge.",
                "reasoning": "Pending LLM judge.",
            },
        )

        result.status = "partially_scored"
        if len(selected_video_ids) != 3:
            result.notes.append(
                f"Expected 3 selected videos for production scoring, got {len(selected_video_ids)}."
            )
        result.notes.append(
            "Only algorithmic dimensions are scored here; LLM-judged dimensions remain pending."
        )
        return result

    def pending_dimension_names(self, result: EvaluationResult) -> list[str]:
        """Return the names of any dimensions that have not yet received a score."""
        return [dimension.name for dimension in result.dimensions if dimension.score is None]

    def select_video_ids(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Resolve which video IDs a skill run should use, executing the strategy when needed."""
        return self._select_videos_for_request(request, selected_video_ids)

    def _select_videos_for_request(
        self,
        request: EvaluationRequest,
        selected_video_ids: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        """Return video IDs to evaluate — uses caller-supplied IDs if provided, otherwise runs the skill executor."""
        if selected_video_ids is not None:
            return selected_video_ids, []

        execution = self._skill_executor.execute(request.skill, request.videos)
        return execution.selected_video_ids, execution.notes

    def _apply_llm_scores(
        self,
        result: EvaluationResult,
        request: EvaluationRequest,
    ) -> None:
        """Call the LLM judge to score relevance, substance, and reasoning, then write results into the result object."""
        selected_videos = self.resolve_selected_videos(request, result.selected_video_ids)
        llm_scores, llm_details = self._get_llm_judge().judge_dimensions(
            request,
            selected_videos,
        )
        self.apply_dimension_scores(result, llm_scores, details=llm_details)
        result.notes.append("Applied LLM-judged scores for relevance, substance, and reasoning.")

    def _apply_optional_scores(
        self,
        result: EvaluationResult,
        extra_scores: dict[str, float] | None,
        extra_details: dict[str, str] | None,
    ) -> None:
        """Apply any caller-supplied override scores or detail strings to the result, if provided."""
        if not extra_scores and not extra_details:
            return

        self.apply_dimension_scores(
            result,
            extra_scores or {},
            details=extra_details,
        )

    def _finalize_result(self, result: EvaluationResult) -> EvaluationResult:
        """Mark the result as partially_scored if any dimensions are missing, or compute the final weighted score."""
        pending_dimensions = self.pending_dimension_names(result)
        if pending_dimensions:
            result.status = "partially_scored"
            result.notes.append("Pending dimensions: " + ", ".join(pending_dimensions))
            return result

        return self.aggregate_weighted_score(result)

    def score(
        self,
        skill_path: str,
        cache_path: str,
        selected_video_ids: list[str] | None = None,
        feedback_path: str | None = FEEDBACK_FILE,
        extra_scores: dict[str, float] | None = None,
        extra_details: dict[str, str] | None = None,
        use_llm_judging: bool = False,
    ) -> EvaluationResult:
        """Run the full evaluation pipeline — load, select, score algorithmically, optionally judge with LLM, and finalise."""
        request = self.load_request(
            skill_path=skill_path,
            cache_path=cache_path,
            feedback_path=feedback_path,
        )
        selected_video_ids, execution_notes = self.select_video_ids(
            request,
            selected_video_ids,
        )

        result = self.score_algorithmic_dimensions(request, selected_video_ids)
        result.notes.extend(execution_notes)

        if use_llm_judging:
            self._apply_llm_scores(result, request)

        self._apply_optional_scores(result, extra_scores, extra_details)
        return self._finalize_result(result)


def _parse_cli_selected_ids(raw_selected_ids: str | None) -> list[str] | None:
    if not raw_selected_ids:
        return None
    return [
        video_id.strip()
        for video_id in raw_selected_ids.split(",")
        if video_id.strip()
    ]


def _build_cli_output(evaluator: Evaluator, args: Any) -> dict[str, Any]:
    request = evaluator.load_request(
        skill_path=args.skill,
        cache_path=args.cache,
        feedback_path=args.feedback,
    )
    selected_video_ids = _parse_cli_selected_ids(args.selected_ids)
    extra_scores = json.loads(args.extra_scores_json) if args.extra_scores_json else None
    extra_details = json.loads(args.extra_details_json) if args.extra_details_json else None
    result = evaluator.score(
        skill_path=args.skill,
        cache_path=args.cache,
        selected_video_ids=selected_video_ids,
        feedback_path=args.feedback,
        extra_scores=extra_scores,
        extra_details=extra_details,
        use_llm_judging=args.with_llm_judge,
    )
    return {
        "request": {
            "skill_name": request.skill.name,
            "strategy": request.skill.strategy,
            "video_count": len(request.videos),
            "feedback_entries": len(request.feedback_history),
            "cache_path": request.cache_path,
            "feedback_path": request.feedback_path,
        },
        "result": result.to_dict(),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Load evaluator inputs and print the contract.")
    parser.add_argument("--skill", required=True, help="Path to the candidate SKILL.md file")
    parser.add_argument("--cache", required=True, help="Path to a cached video JSON file")
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        help="Optional path to feedback JSON",
    )
    parser.add_argument(
        "--selected-ids",
        help="Comma-separated selected video IDs for algorithmic scoring",
    )
    parser.add_argument(
        "--extra-scores-json",
        help="Optional JSON object with additional dimension scores",
    )
    parser.add_argument(
        "--extra-details-json",
        help="Optional JSON object with additional dimension details",
    )
    parser.add_argument(
        "--with-llm-judge",
        action="store_true",
        help="Use the configured LLM backend to score relevance, substance, and reasoning",
    )
    args = parser.parse_args()

    evaluator = Evaluator()
    print(json.dumps(_build_cli_output(evaluator, args), indent=2))


if __name__ == "__main__":
    main()
