"""
Tests for adas/evaluator_loader.py

Covers frontmatter parsing and request assembly.
File I/O is tested against real temporary files (no mocking of Path/json)
since the loader's responsibility IS file loading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluator_loader import EvaluationRequestLoader, _parse_frontmatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(path: Path, frontmatter: str = "", body: str = "# Body\n") -> None:
    if frontmatter:
        path.write_text(f"---\n{frontmatter}---\n{body}")
    else:
        path.write_text(body)


def _write_cache(path: Path, videos: list[dict]) -> None:
    path.write_text(json.dumps({
        "fetched_at": "2026-04-30T10:00:00+00:00",
        "count": len(videos),
        "videos": videos,
    }))


def _sample_video_dict(video_id: str = "vid1") -> dict:
    return {
        "video_id": video_id,
        "title": "AI Startup Guide",
        "channel": "TechCasts",
        "channel_id": "ch1",
        "published_at": "2026-04-29T10:00:00Z",
        "description": "A practical guide.",
        "thumbnail": "",
        "query_matched": "AI startup 2026",
        "views": 1000,
        "likes": 50,
        "subscriber_count": 20_000,
        "duration_seconds": 900,
        "tags": [],
        "category_id": "28",
        "views_per_hour": 40.0,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript": None,
    }


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_valid_frontmatter_parsed_correctly(self):
        md = '---\nname: my-skill\nstrategy: recency\nversion: "1.0"\n---\n\n# Body\n'
        meta, body = _parse_frontmatter(md)
        assert meta["name"] == "my-skill"
        assert meta["strategy"] == "recency"
        assert meta["version"] == "1.0"
        assert "# Body" in body

    def test_no_frontmatter_returns_empty_meta_and_full_text(self):
        md = "# Just a heading\n\nSome content."
        meta, body = _parse_frontmatter(md)
        assert meta == {}
        assert body == md

    def test_quoted_value_strips_surrounding_quotes(self):
        meta, _ = _parse_frontmatter('---\nversion: "2.0"\n---\nbody')
        assert meta["version"] == "2.0"

    def test_null_value_kept_as_string(self):
        meta, _ = _parse_frontmatter("---\nscore: null\n---\nbody")
        assert meta["score"] == "null"

    def test_line_without_colon_is_skipped(self):
        meta, _ = _parse_frontmatter("---\nname: skill\nno-colon-line\n---\nbody")
        assert "name" in meta
        assert "no-colon-line" not in meta

    def test_value_with_colon_keeps_full_value(self):
        meta, _ = _parse_frontmatter("---\ndescription: Pick videos: recency first\n---\nbody")
        assert meta["description"] == "Pick videos: recency first"

    def test_no_closing_delimiter_returns_empty_meta(self):
        md = "---\nname: skill\nno closing delimiter"
        meta, body = _parse_frontmatter(md)
        assert meta == {}
        assert body == md

    def test_body_preserves_content_after_delimiter(self):
        _, body = _parse_frontmatter("---\nname: t\n---\n## Steps\n\nDo A.\nDo B.")
        assert "## Steps" in body
        assert "Do A." in body


# ---------------------------------------------------------------------------
# EvaluationRequestLoader.load_skill
# ---------------------------------------------------------------------------

class TestLoadSkill:
    def test_parses_metadata_fields(self, tmp_path):
        p = tmp_path / "SKILL.md"
        _write_skill(p, "name: test-skill\nstrategy: recency\ndescription: Test.\n")
        doc = EvaluationRequestLoader().load_skill(str(p))
        assert doc.name == "test-skill"
        assert doc.strategy == "recency"
        assert doc.description == "Test."

    def test_no_frontmatter_yields_none_name(self, tmp_path):
        p = tmp_path / "SKILL.md"
        _write_skill(p)
        doc = EvaluationRequestLoader().load_skill(str(p))
        assert doc.name is None
        assert doc.strategy is None

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EvaluationRequestLoader().load_skill(str(tmp_path / "nonexistent.md"))


# ---------------------------------------------------------------------------
# EvaluationRequestLoader.load_feedback_history
# ---------------------------------------------------------------------------

class TestLoadFeedbackHistory:
    def test_loads_entries_and_picks_correctly(self, tmp_path):
        f = tmp_path / "feedback.json"
        f.write_text(json.dumps({"history": [{
            "date": "2026-04-30",
            "picks": [
                {"video_id": "vid1", "reaction": "up", "skill_version": "skill_001"},
                {"video_id": "vid2", "reaction": "down"},
            ],
        }]}))
        history = EvaluationRequestLoader().load_feedback_history(str(f))
        assert len(history) == 1
        assert history[0].date == "2026-04-30"
        assert history[0].picks[0].reaction == "up"
        assert history[0].picks[1].reaction == "down"

    def test_missing_file_returns_empty_list(self, tmp_path):
        result = EvaluationRequestLoader().load_feedback_history(str(tmp_path / "missing.json"))
        assert result == []

    def test_empty_history_returns_empty_list(self, tmp_path):
        f = tmp_path / "feedback.json"
        f.write_text(json.dumps({"history": []}))
        assert EvaluationRequestLoader().load_feedback_history(str(f)) == []

    def test_null_reaction_loaded_as_none(self, tmp_path):
        f = tmp_path / "feedback.json"
        f.write_text(json.dumps({"history": [
            {"date": "2026-04-30", "picks": [{"video_id": "v1", "reaction": None}]}
        ]}))
        history = EvaluationRequestLoader().load_feedback_history(str(f))
        assert history[0].picks[0].reaction is None


# ---------------------------------------------------------------------------
# EvaluationRequestLoader.load_request
# ---------------------------------------------------------------------------

class TestLoadRequest:
    def test_assembles_correct_video_count(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        _write_skill(skill_file, "name: test\nstrategy: recency\n")
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, [_sample_video_dict("v1"), _sample_video_dict("v2")])

        request = EvaluationRequestLoader().load_request(
            str(skill_file), str(cache_file), feedback_path=None
        )
        assert len(request.videos) == 2
        assert request.videos[0].video_id == "v1"

    def test_no_feedback_path_yields_empty_history(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        _write_skill(skill_file, "name: test\nstrategy: recency\n")
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, [_sample_video_dict()])

        request = EvaluationRequestLoader().load_request(
            str(skill_file), str(cache_file), feedback_path=None
        )
        assert request.feedback_history == []

    def test_feedback_loaded_when_path_provided(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        _write_skill(skill_file, "name: test\nstrategy: recency\n")
        cache_file = tmp_path / "cache.json"
        _write_cache(cache_file, [_sample_video_dict()])
        feedback_file = tmp_path / "feedback.json"
        feedback_file.write_text(json.dumps(
            {"history": [{"date": "2026-04-30", "picks": []}]}
        ))

        request = EvaluationRequestLoader().load_request(
            str(skill_file), str(cache_file), feedback_path=str(feedback_file)
        )
        assert len(request.feedback_history) == 1
