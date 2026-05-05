"""Tests for adas.meta.dedupe."""

from __future__ import annotations

import pytest

from adas.meta.dedupe import hash_skill_body, is_duplicate

_SKILL_A = """\
---
name: skill-a
version: "1.0"
strategy: recency
description: First skill.
author: adas-meta
score: null
---

## Goal
Pick fresh AI startup videos every day.

## Steps
1. Filter candidates to English-language videos.
2. Prefer videos published within 48 hours.
3. Select top 3 by recency.

## Fallback
Fall back to the 7-day pool if fewer than 3 fresh videos are found.
"""

_SKILL_A_EXTRA_WHITESPACE = """\
---
name: skill-a
version: "1.0"
strategy: recency
description: First skill.
author: adas-meta
score: null
---

## Goal
Pick  fresh   AI startup  videos every day.

## Steps
1. Filter candidates  to  English-language videos.
2. Prefer  videos published within  48 hours.
3. Select top  3  by recency.

## Fallback
Fall back to the 7-day pool if fewer than  3 fresh videos  are found.
"""

_SKILL_A_DIFFERENT_FRONTMATTER = """\
---
name: skill-a-renamed
version: "2.0"
strategy: engagement-velocity
description: Renamed skill.
author: adas-meta
score: null
---

## Goal
Pick fresh AI startup videos every day.

## Steps
1. Filter candidates to English-language videos.
2. Prefer videos published within 48 hours.
3. Select top 3 by recency.

## Fallback
Fall back to the 7-day pool if fewer than 3 fresh videos are found.
"""

_SKILL_B = """\
---
name: skill-b
version: "1.0"
strategy: engagement-velocity
description: Second skill.
author: adas-meta
score: null
---

## Goal
Pick high-velocity AI startup videos.

## Steps
1. Filter to channels with at least 10 000 subscribers.
2. Rank by views-per-hour descending.
3. Select top 3.

## Fallback
Lower subscriber floor to 1 000 if fewer than 3 candidates remain.
"""


class TestHashSkillBody:
    def test_same_content_produces_same_hash(self):
        assert hash_skill_body(_SKILL_A) == hash_skill_body(_SKILL_A)

    def test_whitespace_only_diff_produces_same_hash(self):
        assert hash_skill_body(_SKILL_A) == hash_skill_body(_SKILL_A_EXTRA_WHITESPACE)

    def test_frontmatter_only_diff_produces_same_hash(self):
        assert hash_skill_body(_SKILL_A) == hash_skill_body(_SKILL_A_DIFFERENT_FRONTMATTER)

    def test_different_body_produces_different_hash(self):
        assert hash_skill_body(_SKILL_A) != hash_skill_body(_SKILL_B)

    def test_empty_skill_is_hashable(self):
        result = hash_skill_body("")
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hex


class TestIsDuplicate:
    def test_empty_archive_returns_false(self, tmp_path):
        assert not is_duplicate(_SKILL_A, str(tmp_path))

    def test_exact_match_returns_true(self, tmp_path):
        skill_dir = tmp_path / "skill_001"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(_SKILL_A)
        assert is_duplicate(_SKILL_A, str(tmp_path))

    def test_whitespace_diff_is_duplicate(self, tmp_path):
        skill_dir = tmp_path / "skill_001"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(_SKILL_A)
        assert is_duplicate(_SKILL_A_EXTRA_WHITESPACE, str(tmp_path))

    def test_frontmatter_only_diff_is_duplicate(self, tmp_path):
        skill_dir = tmp_path / "skill_001"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(_SKILL_A)
        assert is_duplicate(_SKILL_A_DIFFERENT_FRONTMATTER, str(tmp_path))

    def test_genuinely_novel_returns_false(self, tmp_path):
        skill_dir = tmp_path / "skill_001"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(_SKILL_A)
        assert not is_duplicate(_SKILL_B, str(tmp_path))

    def test_multiple_archived_skills_any_match_is_duplicate(self, tmp_path):
        for i, body in enumerate([_SKILL_A, _SKILL_B]):
            d = tmp_path / f"skill_{i:03d}"
            d.mkdir()
            (d / "SKILL.md").write_text(body)
        assert is_duplicate(_SKILL_A, str(tmp_path))
        assert is_duplicate(_SKILL_B, str(tmp_path))

    def test_nonexistent_archive_dir_returns_false(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        assert not is_duplicate(_SKILL_A, missing)
