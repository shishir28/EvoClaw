"""
Data contracts for baseline evaluation runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from evaluator_models import EvaluationResult
except ModuleNotFoundError:
    from adas.evaluator_models import EvaluationResult


@dataclass(slots=True)
class BaselineEvaluationRecord:
    skill_path: str
    result: EvaluationResult | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.result is not None and self.error is None

    @property
    def skill_name(self) -> str:
        if self.result is not None:
            return self.result.skill_name
        return Path(self.skill_path).stem

    @property
    def total_score(self) -> float | None:
        if self.result is None:
            return None
        return self.result.total_score

    @property
    def status(self) -> str:
        if self.error is not None:
            return "failed"
        if self.result is None:
            return "pending"
        return self.result.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_path": self.skill_path,
            "skill_name": self.skill_name,
            "status": self.status,
            "total_score": self.total_score,
            "error": self.error,
            "result": self.result.to_dict() if self.result is not None else None,
        }
