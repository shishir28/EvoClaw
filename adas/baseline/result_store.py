"""
Persistence for Step 5 baseline evaluation outputs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from ..utils.paths import write_text_atomic
    from .models import BaselineEvaluationRecord
except ImportError:
    from utils.paths import write_text_atomic
    from baseline.models import BaselineEvaluationRecord


class EvaluationResultStore:
    def __init__(
        self,
        generated_at_factory: Callable[[], str] | None = None,
    ) -> None:
        self._generated_at_factory = generated_at_factory or self._default_generated_at

    def save_run(
        self,
        records: list[BaselineEvaluationRecord],
        output_dir: str,
    ) -> dict[str, Any]:
        destination = Path(output_dir)
        results_dir = destination / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        for record in records:
            record_path = results_dir / f"{Path(record.skill_path).stem}.json"
            write_text_atomic(
                record_path,
                json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
            )

        summary = self._build_summary(records)
        write_text_atomic(
            destination / "summary.json",
            json.dumps(summary, indent=2, ensure_ascii=False),
        )
        return summary

    def _build_summary(self, records: list[BaselineEvaluationRecord]) -> dict[str, Any]:
        ranking = sorted(
            [
                {
                    "skill_path": record.skill_path,
                    "skill_name": record.skill_name,
                    "total_score": record.total_score,
                    "status": record.status,
                }
                for record in records
                if record.total_score is not None
            ],
            key=lambda item: (-float(item["total_score"]), str(item["skill_name"])),
        )

        return {
            "generated_at": self._generated_at_factory(),
            "skills": [
                {
                    "skill_path": record.skill_path,
                    "skill_name": record.skill_name,
                    "status": record.status,
                    "total_score": record.total_score,
                    "error": record.error,
                    "result_file": f"results/{Path(record.skill_path).stem}.json",
                }
                for record in records
            ],
            "ranking": ranking,
        }

    @staticmethod
    def _default_generated_at() -> str:
        return datetime.now(timezone.utc).isoformat()
