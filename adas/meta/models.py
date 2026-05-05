"""Shared DTOs for the Step 9 meta-agent flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candidate:
    thought: str
    name: str
    skill_md: str


@dataclass(frozen=True)
class MetaContext:
    archive_index_json: str
    archive_skill_summaries_json: str
    best_skill_md: str
    recent_feedback_summary_json: str
    design_goal: str


@dataclass(frozen=True)
class ReflectionResult:
    verdict: str  # "accept" or "revise"
    issues: list[str]
    checks: dict[str, bool]
    thought: str
    candidate: Candidate  # possibly-repaired version; always present


@dataclass
class CycleResult:
    outcome: str  # "success" | "dedupe" | "parse_failure" | "reflect_exhausted" | "eval_error"
    candidate: Candidate | None = None
    eval_result: Any | None = None
    skill_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise the cycle outcome to a JSON-safe dict for CLI output."""
        return {
            "outcome": self.outcome,
            "candidate_name": self.candidate.name if self.candidate else None,
            "total_score": (
                self.eval_result.total_score if self.eval_result is not None else None
            ),
            "skill_id": self.skill_id,
            "error": self.error,
        }
