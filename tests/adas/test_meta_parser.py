"""Tests for adas.meta.parser."""

from __future__ import annotations

import json

import pytest

from adas.meta.parser import (
    Candidate,
    extract_candidate,
    parse_frontmatter,
    parse_response,
    strip_fences,
    validate_candidate,
    validate_frontmatter,
)

_VALID_SKILL_MD = """\
---
name: test-skill
version: "1.0"
strategy: recency
description: A test skill.
author: adas-meta
score: null
---

## Goal
Pick the 3 most recently published AI and startup videos from the last 48 hours.
Focus on breaking news, product launches, and founder insights that have not yet gone viral.

## Steps
1. Filter candidates by published_at descending (newest first).
2. Discard videos from channels with fewer than 1,000 subscribers.
3. Discard non-English titles or descriptions.
4. Select the top 3 remaining videos.
5. Generate a one-sentence "why watch" summary for each pick.

## Fallback
Use a wider 96-hour window if fewer than 3 candidates remain after filtering.

Telegram: List top 3 picks with titles, channels, and why-watch summaries.
"""


class TestStripFences:
    def test_json_fence_removed(self):
        raw = '```json\n{"key": 1}\n```'
        assert strip_fences(raw) == '{"key": 1}'

    def test_plain_fence_removed(self):
        raw = '```\n{"key": 1}\n```'
        assert strip_fences(raw) == '{"key": 1}'

    def test_no_fence_unchanged(self):
        raw = '{"key": 1}'
        assert strip_fences(raw) == raw

    def test_empty_string(self):
        assert strip_fences("") == ""

    def test_fence_with_trailing_whitespace(self):
        raw = "```json  \n{}\n```  "
        assert strip_fences(raw) == "{}"


class TestParseResponse:
    def test_valid_json_object(self):
        raw = '{"thought": "ok", "name": "x", "skill_md": "---"}'
        parsed = parse_response(raw)
        assert parsed["thought"] == "ok"

    def test_json_inside_fences(self):
        raw = '```json\n{"thought": "t", "name": "n", "skill_md": "s"}\n```'
        parsed = parse_response(raw)
        assert parsed["name"] == "n"

    def test_json_embedded_in_prose(self):
        raw = 'Here is the result:\n{"thought": "ok", "name": "x", "skill_md": "y"}\nDone.'
        parsed = parse_response(raw)
        assert parsed["thought"] == "ok"

    def test_malformed_raises_value_error(self):
        with pytest.raises(ValueError, match="valid JSON"):
            parse_response("this is not JSON at all!!!")

    def test_array_raises_value_error(self):
        with pytest.raises(ValueError, match="valid JSON"):
            parse_response("[1, 2, 3]")


class TestExtractCandidate:
    def test_valid_returns_candidate(self):
        parsed = {"thought": "rationale", "name": "my-skill", "skill_md": "---\n---\n"}
        c = extract_candidate(parsed)
        assert isinstance(c, Candidate)
        assert c.thought == "rationale"
        assert c.name == "my-skill"
        assert c.skill_md == "---\n---\n"

    def test_missing_thought_raises(self):
        with pytest.raises(ValueError, match="thought"):
            extract_candidate({"name": "x", "skill_md": "y"})

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            extract_candidate({"thought": "x", "skill_md": "y"})

    def test_missing_skill_md_raises(self):
        with pytest.raises(ValueError, match="skill_md"):
            extract_candidate({"thought": "x", "name": "y"})

    def test_non_string_thought_raises(self):
        with pytest.raises(ValueError, match="string"):
            extract_candidate({"thought": 42, "name": "x", "skill_md": "y"})

    def test_non_string_name_raises(self):
        with pytest.raises(ValueError, match="string"):
            extract_candidate({"thought": "x", "name": [], "skill_md": "y"})


class TestParseFrontmatter:
    def test_parses_all_fields(self):
        fm = parse_frontmatter(_VALID_SKILL_MD)
        assert fm["name"] == "test-skill"
        assert fm["strategy"] == "recency"
        assert fm["author"] == "adas-meta"
        assert fm["score"] is None

    def test_null_variants(self):
        md = "---\nname: x\nversion: 1\nstrategy: recency\ndescription: d\nauthor: adas-meta\nscore: null\n---\n"
        fm = parse_frontmatter(md)
        assert fm["score"] is None

    def test_no_opening_fence_raises(self):
        with pytest.raises(ValueError, match="frontmatter"):
            parse_frontmatter("# Just a title\n\nNo frontmatter here.")

    def test_unclosed_frontmatter_raises(self):
        with pytest.raises(ValueError, match="closed"):
            parse_frontmatter("---\nname: test\n")


class TestValidateFrontmatter:
    def test_valid_passes(self):
        fm = validate_frontmatter(_VALID_SKILL_MD)
        assert fm["name"] == "test-skill"

    def test_wrong_author_raises(self):
        bad = _VALID_SKILL_MD.replace("author: adas-meta", "author: human")
        with pytest.raises(ValueError, match="adas-meta"):
            validate_frontmatter(bad)

    def test_missing_author_raises(self):
        lines = [l for l in _VALID_SKILL_MD.split("\n") if not l.startswith("author:")]
        bad = "\n".join(lines)
        with pytest.raises(ValueError, match="author"):
            validate_frontmatter(bad)

    def test_non_null_score_raises(self):
        bad = _VALID_SKILL_MD.replace("score: null", "score: 7.5")
        with pytest.raises(ValueError, match="score"):
            validate_frontmatter(bad)

    def test_unsupported_strategy_raises(self):
        bad = _VALID_SKILL_MD.replace("strategy: recency", "strategy: custom")
        with pytest.raises(ValueError, match="strategy"):
            validate_frontmatter(bad)

    def test_each_supported_strategy_passes(self):
        for strategy in ("recency", "engagement-velocity", "llm-substance-judge"):
            md = _VALID_SKILL_MD.replace("strategy: recency", f"strategy: {strategy}")
            fm = validate_frontmatter(md)
            assert fm["strategy"] == strategy

    def test_missing_description_raises(self):
        lines = [l for l in _VALID_SKILL_MD.split("\n") if not l.startswith("description:")]
        bad = "\n".join(lines)
        with pytest.raises(ValueError, match="description"):
            validate_frontmatter(bad)


class TestValidateCandidate:
    def test_matching_name_passes(self):
        candidate = Candidate(
            thought="ok",
            name="test-skill",
            skill_md=_VALID_SKILL_MD,
        )
        fm = validate_candidate(candidate)
        assert fm["name"] == "test-skill"

    def test_name_mismatch_raises(self):
        candidate = Candidate(
            thought="ok",
            name="different",
            skill_md=_VALID_SKILL_MD,
        )
        with pytest.raises(ValueError, match="Candidate name must match"):
            validate_candidate(candidate)
