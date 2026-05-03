"""
Step 5 orchestration for running and persisting baseline comparisons.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

try:
    from baseline_catalog import BaselineCatalog
    from baseline_evaluation_runner import BaselineEvaluationRunner
    from config import BASELINE_RESULTS_DIR, FEEDBACK_FILE
    from evaluation_result_store import EvaluationResultStore
    from evaluator import Evaluator
except ModuleNotFoundError:
    from adas.baseline_catalog import BaselineCatalog
    from adas.baseline_evaluation_runner import BaselineEvaluationRunner
    from adas.config import BASELINE_RESULTS_DIR, FEEDBACK_FILE
    from adas.evaluation_result_store import EvaluationResultStore
    from adas.evaluator import Evaluator


class BaselineSkillCatalogProtocol(Protocol):
    def skill_paths(self) -> list[str]: ...


class BaselineEvaluationRunnerProtocol(Protocol):
    def run(
        self,
        skill_paths: list[str],
        cache_path: str,
        feedback_path: str | None = None,
        use_llm_judging: bool = False,
    ) -> list[Any]: ...


class EvaluationResultStoreProtocol(Protocol):
    def save_run(self, records: list[Any], output_dir: str) -> dict[str, Any]: ...


class BaselineComparisonService:
    def __init__(
        self,
        catalog: BaselineSkillCatalogProtocol,
        runner: BaselineEvaluationRunnerProtocol,
        store: EvaluationResultStoreProtocol,
        default_output_root: str = BASELINE_RESULTS_DIR,
    ) -> None:
        self._catalog = catalog
        self._runner = runner
        self._store = store
        self._default_output_root = Path(default_output_root)

    def compare(
        self,
        cache_path: str,
        output_dir: str | None = None,
        feedback_path: str | None = FEEDBACK_FILE,
        use_llm_judging: bool = True,
    ) -> dict[str, Any]:
        resolved_cache_path = self._resolve_existing_input_path(cache_path)
        resolved_feedback_path = self._resolve_existing_input_path(feedback_path)
        skill_paths = self._catalog.skill_paths()
        records = self._runner.run(
            skill_paths=skill_paths,
            cache_path=resolved_cache_path,
            feedback_path=resolved_feedback_path,
            use_llm_judging=use_llm_judging,
        )
        resolved_output_dir = self._resolve_output_dir(resolved_cache_path, output_dir)
        summary = self._store.save_run(records, str(resolved_output_dir))
        return {
            "cache_path": resolved_cache_path,
            "output_dir": str(resolved_output_dir),
            "summary": summary,
        }

    def _resolve_output_dir(self, cache_path: str, output_dir: str | None) -> Path:
        if output_dir is not None:
            return Path(output_dir)
        return self._default_output_root / Path(cache_path).stem

    @staticmethod
    def _resolve_existing_input_path(path: str | None) -> str | None:
        if path is None:
            return None
        candidate = Path(path)
        if candidate.exists():
            return str(candidate.resolve())
        return path


def build_default_service() -> BaselineComparisonService:
    return BaselineComparisonService(
        catalog=BaselineCatalog(),
        runner=BaselineEvaluationRunner(Evaluator()),
        store=EvaluationResultStore(),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Step 5 baseline comparisons against one cache."
    )
    parser.add_argument(
        "--cache",
        required=True,
        help="Path to the cached video JSON file to evaluate against.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional output directory for Step 5 results. Defaults to adas/baseline_results/<cache-stem>/.",
    )
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        help="Optional path to feedback history JSON.",
    )
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="Disable loading feedback history for the comparison run.",
    )
    parser.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Skip LLM-judged dimensions and store only algorithmic comparison outputs.",
    )
    args = parser.parse_args()

    service = build_default_service()
    result = service.compare(
        cache_path=args.cache,
        output_dir=args.output_dir,
        feedback_path=None if args.no_feedback else args.feedback,
        use_llm_judging=not args.no_llm_judge,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
