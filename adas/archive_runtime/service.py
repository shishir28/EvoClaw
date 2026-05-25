"""
Step 6 orchestration for writing evaluated skills into the archive.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)

from adas.archive_runtime.models import ArchiveIndex, ArchiveIndexEntry
from adas.archive_runtime.store import ArchiveStore
from adas.baseline.models import BaselineEvaluationRecord


class ArchiveService:
    def __init__(
        self,
        store: ArchiveStore | None = None,
        archived_at_factory: Callable[[], str] | None = None,
    ) -> None:
        self._store = store or ArchiveStore()
        self._archived_at_factory = archived_at_factory or self._default_archived_at

    def archive_records(
        self,
        records: list[BaselineEvaluationRecord],
        source_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        index = self._store.load_index()
        _log.info("archiving %d records (source_type=%s)", len(records), source_type)
        for record in records:
            self._archive_record(
                index=index,
                record=record,
                source_type=source_type,
                context=context,
            )
        self._refresh_best_skill(index)
        self._store.save_index(index)
        _log.info("archive saved; best_skill_id=%s score=%s", index.best_skill_id, index.best_score)
        return index.to_dict()

    def _archive_record(
        self,
        index: ArchiveIndex,
        record: BaselineEvaluationRecord,
        source_type: str,
        context: dict[str, Any],
    ) -> None:
        _log.debug("archiving skill_path=%s status=%s", record.skill_path, record.status)
        # Failed records are archived intentionally so the archive keeps an audit
        # trail of attempted evaluations, not just successful winners.
        resolved_skill_path = self._resolve_skill_path(record.skill_path)
        skill_text = Path(resolved_skill_path).read_text()
        archive_key = self._build_archive_key(source_type, resolved_skill_path, context)
        archived_at = self._archived_at_factory()
        skill_id = self._store.resolve_skill_id(index, archive_key)
        archive_path = skill_id
        entry = ArchiveIndexEntry(
            skill_id=skill_id,
            skill_name=record.skill_name,
            source_type=source_type,
            archive_key=archive_key,
            archive_path=archive_path,
            archived_at=archived_at,
            origin_skill_path=resolved_skill_path,
            status=record.status,
            total_score=record.total_score,
            strategy=record.result.strategy if record.result is not None else None,
            error=record.error,
            context=dict(context),
        )
        # This write order is not atomic: entry files are written before the index
        # is updated and saved. That leaves a small orphaned-files risk on later
        # failures, but keeps each archive entry self-contained on disk.
        self._store.write_entry_files(
            skill_id=skill_id,
            skill_text=skill_text,
            result_payload=record.to_dict(),
            meta_payload=entry.to_dict(),
        )
        self._upsert_index_entry(index, entry)

    @staticmethod
    def _resolve_skill_path(skill_path: str) -> str:
        candidate = Path(skill_path)
        if candidate.exists():
            return str(candidate.resolve())
        raise FileNotFoundError(f"Archived skill file does not exist: {skill_path}")

    @staticmethod
    def _build_archive_key(
        source_type: str,
        skill_path: str,
        context: dict[str, Any],
    ) -> str:
        normalized_context = json.dumps(context, sort_keys=True, ensure_ascii=False)
        return f"{source_type}:{skill_path}:{normalized_context}"

    @staticmethod
    def _upsert_index_entry(index: ArchiveIndex, entry: ArchiveIndexEntry) -> None:
        for i, existing in enumerate(index.skills):
            if existing.skill_id == entry.skill_id:
                index.skills[i] = entry
                return
        index.skills.append(entry)

    @staticmethod
    def _refresh_best_skill(index: ArchiveIndex) -> None:
        scored_entries = [entry for entry in index.skills if entry.total_score is not None]
        if not scored_entries:
            index.best_skill_id = None
            index.best_score = 0.0
            return
        best_entry = sorted(
            scored_entries,
            # Ties fall back to skill_id for deterministic ordering across runs.
            key=lambda item: (-float(item.total_score), item.skill_id),
        )[0]
        index.best_skill_id = best_entry.skill_id
        index.best_score = float(best_entry.total_score)

    @staticmethod
    def _default_archived_at() -> str:
        return datetime.now(timezone.utc).isoformat()
