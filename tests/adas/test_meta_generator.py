"""Tests for adas.meta.generator."""

from __future__ import annotations

import json

import pytest

from adas.meta.models import Candidate, MetaContext
from adas.meta.generator import Generator

_SKILL_MD = (
    "---\n"
    "name: engagement-v2\n"
    'version: "1.0"\n'
    "strategy: engagement-velocity\n"
    "description: High-velocity AI startup picks.\n"
    "author: adas-meta\n"
    "score: null\n"
    "---\n"
    "\n"
    "## Goal\n"
    "Pick fast-moving AI startup videos.\n"
    "\n"
    "## Steps\n"
    "1. Filter to channels with >= 10 000 subscribers.\n"
    "2. Rank by views-per-hour descending.\n"
    "3. Select top 3.\n"
    "\n"
    "## Fallback\n"
    "Lower subscriber floor to 1 000 if fewer than 3 qualify.\n"
)


def _two_part(head: dict, skill_md: str | None = None) -> str:
    """Build a meta-agent response: a JSON head, then a fenced SKILL.md block."""
    out = json.dumps(head)
    if skill_md is not None:
        out += f"\n\n```markdown\n{skill_md}```\n"
    return out


_VALID_RESPONSE = _two_part(
    {
        "thought": "Engagement velocity improves pick quality.",
        "name": "engagement-v2",
    },
    _SKILL_MD,
)


def _make_context(design_goal: str = "") -> MetaContext:
    return MetaContext(
        archive_index_json="{}",
        archive_skill_summaries_json="[]",
        best_skill_md="",
        recent_feedback_summary_json="{}",
        design_goal=design_goal,
    )


class _FakeClient:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete(
        self, system_prompt: str, user_prompt: str, json_schema: dict | None = None
    ) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self._response


class TestGenerator:
    def test_returns_candidate_on_valid_response(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("You are the meta-agent.")
        (tmp_path / "meta_design.md").write_text(
            "Design a skill. Goal: DESIGN_GOAL\n"
            "Archive: ARCHIVE_INDEX_JSON\n"
            "Summaries: ARCHIVE_SKILL_SUMMARIES_JSON\n"
            "Best: BEST_SKILL_MD\n"
            "Feedback: RECENT_FEEDBACK_SUMMARY_JSON\n"
        )
        client = _FakeClient(_VALID_RESPONSE)
        gen = Generator(client=client, prompt_dir=str(tmp_path))
        candidate = gen.generate(_make_context())

        assert isinstance(candidate, Candidate)
        assert candidate.name == "engagement-v2"
        assert "engagement-velocity" in candidate.skill_md

    def test_design_goal_substituted_in_user_prompt(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_design.md").write_text("Goal: DESIGN_GOAL")

        client = _FakeClient(_VALID_RESPONSE)
        gen = Generator(client=client, prompt_dir=str(tmp_path))
        gen.generate(_make_context(design_goal="maximize novelty"))

        _, user_prompt = client.calls[0]
        assert "maximize novelty" in user_prompt

    def test_archive_context_substituted_in_user_prompt(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_design.md").write_text("Index: ARCHIVE_INDEX_JSON")

        ctx = MetaContext(
            archive_index_json='{"best_skill_id": "skill_001"}',
            archive_skill_summaries_json="[]",
            best_skill_md="",
            recent_feedback_summary_json="{}",
            design_goal="",
        )
        client = _FakeClient(_VALID_RESPONSE)
        gen = Generator(client=client, prompt_dir=str(tmp_path))
        gen.generate(ctx)

        _, user_prompt = client.calls[0]
        assert "skill_001" in user_prompt

    def test_system_prompt_passed_to_client(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("UNIQUE_SYSTEM_CONTENT")
        (tmp_path / "meta_design.md").write_text("design")

        client = _FakeClient(_VALID_RESPONSE)
        gen = Generator(client=client, prompt_dir=str(tmp_path))
        gen.generate(_make_context())

        system_prompt, _ = client.calls[0]
        assert "UNIQUE_SYSTEM_CONTENT" in system_prompt

    def test_malformed_response_raises_value_error(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_design.md").write_text("design")

        client = _FakeClient("not valid json at all!!!")
        gen = Generator(client=client, prompt_dir=str(tmp_path))

        with pytest.raises(ValueError):
            gen.generate(_make_context())

    def test_missing_skill_md_block_raises_value_error(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_design.md").write_text("design")

        # Valid JSON head but no fenced SKILL.md block.
        bad_response = json.dumps({"thought": "ok", "name": "x"})
        client = _FakeClient(bad_response)
        gen = Generator(client=client, prompt_dir=str(tmp_path))

        with pytest.raises(ValueError, match="SKILL.md document"):
            gen.generate(_make_context())

    def test_missing_head_field_raises_value_error(self, tmp_path):
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_design.md").write_text("design")

        # Fenced block present but JSON head is missing 'name'.
        bad_response = _two_part({"thought": "ok"}, _SKILL_MD)
        client = _FakeClient(bad_response)
        gen = Generator(client=client, prompt_dir=str(tmp_path))

        with pytest.raises(ValueError, match="name"):
            gen.generate(_make_context())
