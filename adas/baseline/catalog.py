"""
Catalog of baseline skill files used for Step 5 comparisons.
"""

from __future__ import annotations

from pathlib import Path

from adas.config import BASELINES_DIR


class BaselineCatalog:
    def __init__(
        self,
        base_dir: str = BASELINES_DIR,
        filenames: tuple[str, ...] = (
            "baseline_recency.md",
            "baseline_popular.md",
            "baseline_curated.md",
        ),
    ) -> None:
        self._base_dir = Path(base_dir)
        self._filenames = filenames

    def skill_paths(self) -> list[str]:
        paths = [self._base_dir / filename for filename in self._filenames]
        missing_paths = [path for path in paths if not path.exists()]
        if missing_paths:
            raise FileNotFoundError(
                "Missing baseline skill file(s): "
                + ", ".join(str(path) for path in missing_paths)
            )
        return [str(path) for path in paths]
