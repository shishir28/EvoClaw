"""
Step 5 orchestration for running and persisting baseline comparisons.
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any, Protocol

from adas.archive_runtime.service import ArchiveService
from adas.config import BASELINE_RESULTS_DIR, FEEDBACK_FILE
from adas.evaluation.service import Evaluator
from adas.baseline.catalog import BaselineCatalog
from adas.baseline.result_store import EvaluationResultStore
from adas.baseline.runner import BaselineEvaluationRunner


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


class ArchiveServiceProtocol(Protocol):
    def archive_records(
        self,
        records: list[Any],
        source_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class BaselineComparisonService:
    def __init__(
        self,
        catalog: BaselineSkillCatalogProtocol,
        runner: BaselineEvaluationRunnerProtocol,
        store: EvaluationResultStoreProtocol,
        archive_service: ArchiveServiceProtocol | None = None,
        default_output_root: str = BASELINE_RESULTS_DIR,
    ) -> None:
        self._catalog = catalog
        self._runner = runner
        self._store = store
        self._archive_service = archive_service
        self._default_output_root = Path(default_output_root)

    def compare(
        self,
        cache_path: str,
        output_dir: str | None = None,
        feedback_path: str | None = FEEDBACK_FILE,
        use_llm_judging: bool = True,
        archive_results: bool = False,
    ) -> dict[str, Any]:
        resolved_cache_path = self._resolve_required_input_path(cache_path)
        resolved_feedback_path = self._resolve_optional_input_path(feedback_path)
        skill_paths = self._catalog.skill_paths()
        records = self._runner.run(
            skill_paths=skill_paths,
            cache_path=resolved_cache_path,
            feedback_path=resolved_feedback_path,
            use_llm_judging=use_llm_judging,
        )
        resolved_output_dir = self._resolve_output_dir(resolved_cache_path, output_dir)
        summary = self._store.save_run(records, str(resolved_output_dir))
        response = {
            "cache_path": resolved_cache_path,
            "output_dir": str(resolved_output_dir),
            "summary": summary,
        }
        if archive_results:
            if self._archive_service is None:
                raise ValueError("Archive service is not configured for this comparison run.")
            response["archive"] = self._archive_service.archive_records(
                records=records,
                source_type="baseline",
                context={
                    "cache_path": resolved_cache_path,
                    "feedback_path": resolved_feedback_path,
                    "use_llm_judging": use_llm_judging,
                },
            )
        return response

    def _resolve_output_dir(self, cache_path: str, output_dir: str | None) -> Path:
        if output_dir is not None:
            return Path(output_dir)
        return self._default_output_root / Path(cache_path).stem

    @staticmethod
    def _resolve_required_input_path(path: str) -> str:
        candidate = Path(path)
        if candidate.exists():
            return str(candidate.resolve())
        raise FileNotFoundError(f"Required input file does not exist: {path}")

    @staticmethod
    def _resolve_optional_input_path(path: str | None) -> str | None:
        if path is None:
            return None
        candidate = Path(path)
        if candidate.exists():
            return str(candidate.resolve())
        return path


def build_default_service() -> BaselineComparisonService:
    """Compose the default baseline comparison service for CLI usage."""
    return BaselineComparisonService(
        catalog=BaselineCatalog(),
        runner=BaselineEvaluationRunner(Evaluator()),
        store=EvaluationResultStore(),
        archive_service=ArchiveService(),
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the baseline comparison CLI parser."""
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
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also archive the evaluated skill outputs into adas/archive/skill_### entries.",
    )
    return parser


def _run_comparison_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Execute a baseline comparison from parsed CLI arguments."""
    service = build_default_service()
    return service.compare(
        cache_path=args.cache,
        output_dir=args.output_dir,
        feedback_path=None if args.no_feedback else args.feedback,
        use_llm_judging=not args.no_llm_judge,
        archive_results=args.archive,
    )


def main() -> None:
    """Parse CLI args, run baseline comparison, and print JSON output."""
    args = _build_parser().parse_args()
    result = _run_comparison_from_args(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
