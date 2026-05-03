"""
Data contracts for Step 6 archive entries and index state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ArchiveIndexEntry:
    skill_id: str
    skill_name: str
    source_type: str
    archive_key: str
    archive_path: str
    archived_at: str
    origin_skill_path: str
    status: str
    total_score: float | None
    strategy: str | None = None
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArchiveIndexEntry":
        return cls(
            skill_id=payload["skill_id"],
            skill_name=payload.get("skill_name", ""),
            source_type=payload.get("source_type", ""),
            archive_key=payload.get("archive_key", ""),
            archive_path=payload.get("archive_path", ""),
            archived_at=payload.get("archived_at", ""),
            origin_skill_path=payload.get("origin_skill_path", ""),
            status=payload.get("status", "pending"),
            total_score=payload.get("total_score"),
            strategy=payload.get("strategy"),
            error=payload.get("error"),
            context=dict(payload.get("context", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArchiveIndex:
    best_skill_id: str | None = None
    best_score: float = 0.0
    skills: list[ArchiveIndexEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArchiveIndex":
        return cls(
            best_skill_id=payload.get("best_skill_id"),
            best_score=float(payload.get("best_score", 0.0) or 0.0),
            skills=[
                ArchiveIndexEntry.from_dict(entry)
                for entry in payload.get("skills", [])
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_skill_id": self.best_skill_id,
            "best_score": self.best_score,
            "skills": [entry.to_dict() for entry in self.skills],
        }
