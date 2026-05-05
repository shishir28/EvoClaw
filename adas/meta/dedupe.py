"""Hash-based novelty check for candidate skills.

Normalises whitespace and strips frontmatter before hashing so that
trivial metadata edits (version bump, score field) don't count as novel.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def _strip_frontmatter(skill_md: str) -> str:
    """Return only the body of *skill_md* with the YAML frontmatter block removed.
    This ensures metadata-only edits (version bump, score field) don't count as novel."""
    lines = skill_md.split("\n")
    if not lines or lines[0].strip() != "---":
        return skill_md
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :])
    return skill_md


def _normalize(text: str) -> str:
    """Collapse all whitespace runs to a single space so incidental formatting
    differences don't produce different hashes for identical logic."""
    return re.sub(r"\s+", " ", text).strip()


def hash_skill_body(skill_md: str) -> str:
    """Return the SHA-256 hex digest of the normalised skill body (frontmatter excluded).
    Two skills with identical logic but different metadata produce the same hash."""
    body = _normalize(_strip_frontmatter(skill_md))
    return hashlib.sha256(body.encode()).hexdigest()


def is_duplicate(candidate_skill_md: str, archive_dir: str) -> bool:
    """Return True if the candidate's body hash matches any SKILL.md in the archive.
    Returns False when the archive directory does not exist, so cold-start cycles proceed."""
    candidate_hash = hash_skill_body(candidate_skill_md)
    for skill_file in Path(archive_dir).glob("*/SKILL.md"):
        if hash_skill_body(skill_file.read_text()) == candidate_hash:
            return True
    return False
