"""Assembles prompt context for the meta-agent from archive state and feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adas.archive_runtime.store import ArchiveStore
from adas.config import ARCHIVE_DIR, FEEDBACK_FILE
from adas.feedback.store import FeedbackStore
from adas.meta.models import MetaContext
from adas.meta.parser import parse_frontmatter

_POSITIVE_REACTIONS: frozenset[str] = frozenset(
    {"up", "thumbs_up", "like", "liked", "positive", "👍"}
)
_NEGATIVE_REACTIONS: frozenset[str] = frozenset(
    {"down", "thumbs_down", "dislike", "disliked", "negative", "👎"}
)

def _build_skill_summary(entry: Any, archive_dir: str) -> dict[str, Any]:
    """Return a compact dict of key archive fields for one skill, appending the
    frontmatter description when the SKILL.md file is present."""
    summary: dict[str, Any] = {
        "skill_id": entry.skill_id,
        "skill_name": entry.skill_name,
        "strategy": entry.strategy,
        "total_score": entry.total_score,
        "archived_at": entry.archived_at,
        "status": entry.status,
    }
    skill_file = Path(archive_dir) / entry.skill_id / "SKILL.md"
    if skill_file.exists():
        try:
            fm = parse_frontmatter(skill_file.read_text())
            if fm.get("description"):
                summary["description"] = fm["description"]
        except ValueError:
            pass
    return summary


def _build_feedback_summary(history: list) -> dict[str, Any]:
    """Distil raw feedback history into liked/disliked channel and topic lists.
    Caps each list to avoid bloating the prompt (channels ≤10, picks ≤20)."""
    liked_channels: list[str] = []
    liked_topics: list[str] = []
    disliked_channels: list[str] = []
    disliked_topics: list[str] = []
    recent_picks: list[dict[str, Any]] = []

    for entry in history:
        for pick in entry.picks:
            snap = pick.snapshot
            if pick.reaction in _POSITIVE_REACTIONS:
                if snap and snap.channel and snap.channel not in liked_channels:
                    liked_channels.append(snap.channel)
                if snap and snap.query_matched and snap.query_matched not in liked_topics:
                    liked_topics.append(snap.query_matched)
            elif pick.reaction in _NEGATIVE_REACTIONS:
                if snap and snap.channel and snap.channel not in disliked_channels:
                    disliked_channels.append(snap.channel)
                if snap and snap.query_matched and snap.query_matched not in disliked_topics:
                    disliked_topics.append(snap.query_matched)
            recent_picks.append(
                {"video_id": pick.video_id, "reaction": pick.reaction, "date": entry.date}
            )

    return {
        "liked_channels": liked_channels[:10],
        "liked_topics": liked_topics[:10],
        "disliked_channels": disliked_channels[:10],
        "disliked_topics": disliked_topics[:10],
        "recent_picks": recent_picks[-20:],
    }


def build_context(
    archive_dir: str = ARCHIVE_DIR,
    feedback_path: str = FEEDBACK_FILE,
    design_goal: str = "",
    archive_store: ArchiveStore | None = None,
    feedback_store: FeedbackStore | None = None,
) -> MetaContext:
    """Assemble all prompt inputs the meta-agent needs to design and evaluate a new skill.
    Feedback is treated as optional; a missing feedback file returns an empty history."""
    store = archive_store or ArchiveStore(archive_dir=archive_dir)
    index = store.load_index()

    archive_index_json = json.dumps(index.to_dict(), indent=2, ensure_ascii=False)
    summaries = [_build_skill_summary(e, archive_dir) for e in index.skills]
    archive_skill_summaries_json = json.dumps(summaries, indent=2, ensure_ascii=False)

    best_skill_md = ""
    if index.best_skill_id:
        skill_file = Path(archive_dir) / index.best_skill_id / "SKILL.md"
        if skill_file.exists():
            best_skill_md = skill_file.read_text()

    fb_store = feedback_store or FeedbackStore()
    try:
        history = fb_store.load_history(feedback_path)
    except (FileNotFoundError, OSError):
        history = []

    recent_feedback_summary_json = json.dumps(
        _build_feedback_summary(history), indent=2, ensure_ascii=False
    )

    return MetaContext(
        archive_index_json=archive_index_json,
        archive_skill_summaries_json=archive_skill_summaries_json,
        best_skill_md=best_skill_md,
        recent_feedback_summary_json=recent_feedback_summary_json,
        design_goal=design_goal,
    )
