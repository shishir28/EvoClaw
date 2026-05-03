"""
Tests for baseline skill discovery.
"""

from __future__ import annotations

import pytest

from baseline.catalog import BaselineCatalog


class TestBaselineCatalog:
    def test_returns_configured_baseline_paths_in_order(self, tmp_path):
        for name in ("a.md", "b.md", "c.md"):
            (tmp_path / name).write_text("# skill\n")

        catalog = BaselineCatalog(
            base_dir=str(tmp_path),
            filenames=("a.md", "b.md", "c.md"),
        )

        assert catalog.skill_paths() == [
            str(tmp_path / "a.md"),
            str(tmp_path / "b.md"),
            str(tmp_path / "c.md"),
        ]

    def test_raises_when_a_baseline_file_is_missing(self, tmp_path):
        (tmp_path / "a.md").write_text("# skill\n")
        catalog = BaselineCatalog(
            base_dir=str(tmp_path),
            filenames=("a.md", "missing.md"),
        )

        with pytest.raises(FileNotFoundError, match="missing.md"):
            catalog.skill_paths()
