"""
Persistence helpers for Step 6 archive entries and index state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from ..config import ARCHIVE_DIR, ARCHIVE_INDEX
    from .models import ArchiveIndex
except ImportError:
    from config import ARCHIVE_DIR, ARCHIVE_INDEX
    from archive_runtime.models import ArchiveIndex


class ArchiveStore:
    def __init__(
        self,
        archive_dir: str = ARCHIVE_DIR,
        archive_index: str | None = None,
    ) -> None:
        self._archive_dir = Path(archive_dir)
        self._archive_index = Path(archive_index) if archive_index else self._archive_dir / "index.json"

    def load_index(self) -> ArchiveIndex:
        if not self._archive_index.exists():
            return ArchiveIndex()
        payload = json.loads(self._archive_index.read_text())
        return ArchiveIndex.from_dict(payload)

    def save_index(self, index: ArchiveIndex) -> None:
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._archive_index.write_text(json.dumps(index.to_dict(), indent=2, ensure_ascii=False))

    def resolve_skill_id(self, index: ArchiveIndex, archive_key: str) -> str:
        for entry in index.skills:
            if entry.archive_key == archive_key:
                return entry.skill_id
        return self._next_skill_id(index)

    def write_entry_files(
        self,
        skill_id: str,
        skill_text: str,
        result_payload: dict[str, Any],
        meta_payload: dict[str, Any],
    ) -> str:
        entry_dir = self._archive_dir / skill_id
        entry_dir.mkdir(parents=True, exist_ok=True)
        (entry_dir / "SKILL.md").write_text(skill_text)
        (entry_dir / "result.json").write_text(
            json.dumps(result_payload, indent=2, ensure_ascii=False)
        )
        (entry_dir / "meta.json").write_text(json.dumps(meta_payload, indent=2, ensure_ascii=False))
        return skill_id

    @staticmethod
    def _next_skill_id(index: ArchiveIndex) -> str:
        existing_numbers = []
        for entry in index.skills:
            suffix = entry.skill_id.removeprefix("skill_")
            if suffix.isdigit():
                existing_numbers.append(int(suffix))
        next_number = max(existing_numbers, default=0) + 1
        return f"skill_{next_number:03d}"
