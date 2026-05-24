"""Promote the best archived skill into the production skill path."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

_log = logging.getLogger(__name__)

try:
    from ..archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
    from ..archive_runtime.store import ArchiveStore
    from ..config import ARCHIVE_DIR, SKILL_PRODUCTION
except ImportError:
    from archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
    from archive_runtime.store import ArchiveStore
    from config import ARCHIVE_DIR, SKILL_PRODUCTION


class ArchiveIndexReader(Protocol):
    """Small protocol for reading archive state.

    Keeps SkillPromoter dependent on a narrow interface instead of a concrete store.
    """

    def load_index(self) -> ArchiveIndex:
        """Return the current archive index snapshot."""
        ...


@dataclass(frozen=True, slots=True)
class DeploymentRecord:
    """Persisted metadata for the skill currently deployed to production.

    The previous fields support simple auditability without a full history table.
    """

    deployed_skill_id: str
    deployed_score: float
    deployed_at: str
    source_skill_path: str
    production_skill_path: str
    previous_skill_id: str | None = None
    previous_score: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "DeploymentRecord":
        """Build a deployment record from JSON-loaded metadata."""
        return cls(
            deployed_skill_id=str(payload["deployed_skill_id"]),
            deployed_score=float(payload["deployed_score"]),
            deployed_at=str(payload.get("deployed_at", "")),
            source_skill_path=str(payload.get("source_skill_path", "")),
            production_skill_path=str(payload.get("production_skill_path", "")),
            previous_skill_id=(
                str(payload["previous_skill_id"])
                if payload.get("previous_skill_id") is not None
                else None
            ),
            previous_score=(
                float(payload["previous_score"])
                if payload.get("previous_score") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation for persistence."""
        return asdict(self)


class DeploymentRecordStore:
    """Load and save deployment metadata beside the production skill."""

    def __init__(self, path: str | Path, history_path: str | Path | None = None) -> None:
        """Create a store bound to a metadata JSON path and append-only history log."""
        self._path = Path(path)
        self._history_path = (
            Path(history_path)
            if history_path is not None
            else self._path.with_name("deployment_history.jsonl")
        )

    @property
    def path(self) -> Path:
        """Expose the metadata path for CLI and result reporting."""
        return self._path

    @property
    def history_path(self) -> Path:
        """Expose the append-only promotion history log path."""
        return self._history_path

    def load(self) -> DeploymentRecord | None:
        """Return the current deployment record, or None before first deploy."""
        if not self._path.exists():
            return None
        payload = json.loads(self._path.read_text())
        return DeploymentRecord.from_dict(payload)

    def load_history(self) -> list[DeploymentRecord]:
        """Return promotion history in append order, oldest to newest."""
        if not self._history_path.exists():
            return []
        history: list[DeploymentRecord] = []
        for line in self._history_path.read_text().splitlines():
            if not line.strip():
                continue
            history.append(DeploymentRecord.from_dict(json.loads(line)))
        return history

    def save(self, record: DeploymentRecord) -> None:
        """Persist deployment metadata using a temp-file replace."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_name(f".{self._path.name}.tmp")
        temp_path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
        temp_path.replace(self._path)

    def append_history(self, record: DeploymentRecord) -> None:
        """Append one successful promotion to the deployment history log."""
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._history_path.read_text().splitlines() if self._history_path.exists() else []
        existing.append(json.dumps(record.to_dict(), ensure_ascii=False))
        temp_path = self._history_path.with_name(f".{self._history_path.name}.tmp")
        temp_path.write_text("\n".join(existing) + "\n")
        temp_path.replace(self._history_path)


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Outcome returned by SkillPromoter for logging and CLI output."""

    status: str
    reason: str
    skill_id: str | None
    score: float | None
    source_skill_path: str | None
    production_skill_path: str
    deployment_record_path: str
    previous_skill_id: str | None = None
    previous_score: float | None = None

    @property
    def promoted(self) -> bool:
        """Convenience flag for callers that only need success vs skip."""
        return self.status == "promoted"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe result including the derived promoted flag."""
        payload = asdict(self)
        payload["promoted"] = self.promoted
        return payload


class SkillPromoter:
    """Deploy the archive winner when it beats the currently deployed skill."""

    def __init__(
        self,
        archive_dir: str = ARCHIVE_DIR,
        production_skill_path: str = SKILL_PRODUCTION,
        archive_store: ArchiveIndexReader | None = None,
        deployment_store: DeploymentRecordStore | None = None,
        deployed_at_factory: Callable[[], str] | None = None,
    ) -> None:
        """Create a promoter with injectable archive and deployment stores."""
        self._archive_dir = Path(archive_dir)
        self._production_skill_path = Path(production_skill_path)
        self._archive_store = archive_store or ArchiveStore(archive_dir)
        self._deployment_store = deployment_store or DeploymentRecordStore(
            self._production_skill_path.with_name("deployment.json")
        )
        self._deployed_at_factory = deployed_at_factory or self._default_deployed_at

    def promote_best_skill(self) -> PromotionResult:
        """Promote the archive winner if its score beats current production."""
        index = self._archive_store.load_index()
        best_entry = self._find_best_entry(index)
        current_record = self._deployment_store.load()

        if best_entry is None:
            _log.info("promotion skipped: archive has no deployable best skill")
            return self._skipped_result(
                reason="Archive index does not contain a deployable best skill.",
                current_record=current_record,
            )

        best_score = float(best_entry.total_score)
        source_skill_path = self._resolve_archived_skill_path(best_entry)

        if self._current_deployment_is_better_or_equal(current_record, best_score):
            _log.info(
                "promotion skipped: current score %.4f >= best score %.4f",
                current_record.deployed_score,
                best_score,
            )
            return self._skipped_result(
                reason="Current deployment score is greater than or equal to archive best score.",
                current_record=current_record,
                best_entry=best_entry,
                source_skill_path=source_skill_path,
            )

        _log.info(
            "promoting skill_id=%s score=%.4f -> %s",
            best_entry.skill_id,
            best_score,
            self._production_skill_path,
        )
        self._copy_skill(source_skill_path, self._production_skill_path)
        record = self._build_deployment_record(
            best_entry=best_entry,
            best_score=best_score,
            source_skill_path=source_skill_path,
            current_record=current_record,
        )
        self._deployment_store.save(record)
        self._deployment_store.append_history(record)
        return self._promoted_result(record)

    @staticmethod
    def _current_deployment_is_better_or_equal(
        current_record: DeploymentRecord | None,
        best_score: float,
    ) -> bool:
        """Return True when production should keep the existing deployed skill."""
        return current_record is not None and current_record.deployed_score >= best_score

    def _build_deployment_record(
        self,
        best_entry: ArchiveIndexEntry,
        best_score: float,
        source_skill_path: Path,
        current_record: DeploymentRecord | None,
    ) -> DeploymentRecord:
        """Create the metadata record for a successful production promotion."""
        return DeploymentRecord(
            deployed_skill_id=best_entry.skill_id,
            deployed_score=best_score,
            deployed_at=self._deployed_at_factory(),
            source_skill_path=str(source_skill_path),
            production_skill_path=str(self._production_skill_path),
            previous_skill_id=(
                current_record.deployed_skill_id if current_record is not None else None
            ),
            previous_score=(
                current_record.deployed_score if current_record is not None else None
            ),
        )

    def _promoted_result(self, record: DeploymentRecord) -> PromotionResult:
        """Build the public result shape for a successful promotion."""
        return PromotionResult(
            status="promoted",
            reason="Archive best skill was promoted to production.",
            skill_id=record.deployed_skill_id,
            score=record.deployed_score,
            source_skill_path=record.source_skill_path,
            production_skill_path=record.production_skill_path,
            deployment_record_path=str(self._deployment_store.path),
            previous_skill_id=record.previous_skill_id,
            previous_score=record.previous_score,
        )

    def _find_best_entry(self, index: ArchiveIndex) -> ArchiveIndexEntry | None:
        """Resolve the best archive entry from the index's best_skill_id."""
        if not index.best_skill_id:
            return None
        for entry in index.skills:
            if entry.skill_id == index.best_skill_id and entry.total_score is not None:
                return entry
        return None

    def _resolve_archived_skill_path(self, entry: ArchiveIndexEntry) -> Path:
        """Return the archived SKILL.md path for a deployable index entry."""
        archive_path = entry.archive_path or entry.skill_id
        skill_path = self._archive_dir / archive_path / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Archived skill file does not exist: {skill_path}")
        return skill_path

    def _skipped_result(
        self,
        reason: str,
        current_record: DeploymentRecord | None,
        best_entry: ArchiveIndexEntry | None = None,
        source_skill_path: Path | None = None,
    ) -> PromotionResult:
        """Build a consistent skipped result while preserving current metadata."""
        return PromotionResult(
            status="skipped",
            reason=reason,
            skill_id=best_entry.skill_id if best_entry is not None else None,
            score=(
                float(best_entry.total_score)
                if best_entry is not None and best_entry.total_score is not None
                else None
            ),
            source_skill_path=str(source_skill_path) if source_skill_path else None,
            production_skill_path=str(self._production_skill_path),
            deployment_record_path=str(self._deployment_store.path),
            previous_skill_id=(
                current_record.deployed_skill_id if current_record is not None else None
            ),
            previous_score=(
                current_record.deployed_score if current_record is not None else None
            ),
        )

    @staticmethod
    def _copy_skill(source: Path, destination: Path) -> None:
        """Copy SKILL.md through a temp path so partial writes are avoided."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f".{destination.name}.tmp")
        temp_path.write_text(source.read_text())
        temp_path.replace(destination)

    @staticmethod
    def _default_deployed_at() -> str:
        """Return the default UTC deployment timestamp."""
        return datetime.now(timezone.utc).isoformat()
