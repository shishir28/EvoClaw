"""Persistence helpers for delivery metadata."""

from __future__ import annotations

import json
from pathlib import Path

from adas.telegram.models import DeliveryRecord
from adas.config import BASE_DIR
from adas.utils.paths import assert_safe_write_path


class DeliveryLogStore:
    """Append-only JSON persistence for Telegram digest delivery records."""

    def __init__(self, path: str | Path, safe_base: Path | None = None) -> None:
        self._path = Path(path)
        self._safe_base: Path = safe_base if safe_base is not None else Path(BASE_DIR)

    @property
    def path(self) -> Path:
        return self._path

    def load_history(self) -> list[DeliveryRecord]:
        if not self._path.exists():
            return []
        payload = json.loads(self._path.read_text())
        raw_history = payload.get("history", [])
        if not isinstance(raw_history, list):
            raise ValueError("Delivery log must contain a top-level 'history' list.")
        return [
            DeliveryRecord.from_dict(entry)
            for entry in raw_history
            if isinstance(entry, dict)
        ]

    def append(self, record: DeliveryRecord) -> None:
        assert_safe_write_path(self._path, self._safe_base)
        history = self.load_history()
        history.append(record)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_name(f".{self._path.name}.tmp")
        temp_path.write_text(
            json.dumps(
                {"history": [entry.to_dict() for entry in history]},
                indent=2,
                ensure_ascii=False,
            )
        )
        temp_path.replace(self._path)
