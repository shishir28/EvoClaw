"""
Persistence helpers for Step 7 feedback history.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

try:
    from ..config import FEEDBACK_FILE
    from ..evaluation.models import FeedbackEntry
except ImportError:
    from config import FEEDBACK_FILE
    from evaluation.models import FeedbackEntry


class FeedbackStore:
    def __init__(self, default_path: str = FEEDBACK_FILE) -> None:
        self._default_path = Path(default_path)

    def load_history(self, path: str | None = None) -> list[FeedbackEntry]:
        resolved = Path(path) if path is not None else self._default_path
        if not resolved.exists():
            return []
        payload = json.loads(resolved.read_text())
        history = payload.get("history", [])
        return [FeedbackEntry.from_dict(entry) for entry in history]

    def save_history(self, history: list[FeedbackEntry], path: str | None = None) -> None:
        resolved = Path(path) if path is not None else self._default_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"history": [entry.to_dict() for entry in history]},
            indent=2,
            ensure_ascii=False,
        )
        # Write to a temp file in the same directory then rename so a crash
        # mid-write cannot leave feedback.json in a partially-written state.
        fd, tmp_path = tempfile.mkstemp(dir=resolved.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, resolved)
        except Exception:
            os.unlink(tmp_path)
            raise
