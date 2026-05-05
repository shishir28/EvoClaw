"""Tests for adas.meta.reflector."""

from __future__ import annotations

import json

import pytest

from adas.meta.models import Candidate, MetaContext, ReflectionResult
from adas.meta.reflector import Reflector

_SKILL_MD = (
    "---\n"
    "name: my-skill\n"
    'version: "1.0"\n'
    "strategy: recency\n"
    "description: A test skill.\n"
    "author: adas-meta\n"
    "score: null\n"
    "---\n"
    "\n"
    "## Goal\n"
    "Pick fresh AI videos.\n"
    "\n"
    "## Steps\n"
    "1. Filter by recency.\n"
    "\n"
    "## Fallback\n"
    "Use 7-day window.\n"
)

_CANDIDATE = Candidate(
    thought="initial thought",
    name="my-skill",
    skill_md=_SKILL_MD,
)

_REPAIRED_SKILL_MD = _SKILL_MD.replace("name: my-skill", "name: my-skill-v2")

_ACCEPT_RESPONSE = json.dumps(
    {
        "verdict": "accept",
        "issues": [],
        "checks": {
            "json_contract": True,
            "frontmatter": True,
            "supported_strategy": True,
            "name_consistency": True,
            "structure": True,
            "coherence": True,
            "novelty": True,
            "runtime_fit": True,
        },
        "thought": "Looks good to go.",
        "name": "my-skill",
        "skill_md": _SKILL_MD,
    }
)

_REVISE_RESPONSE = json.dumps(
    {
        "verdict": "revise",
        "issues": ["Missing meaningful novelty compared to archive."],
        "checks": {
            "json_contract": True,
            "novelty": False,
        },
        "thought": "Needs more differentiation.",
        "name": "my-skill-v2",
        "skill_md": _REPAIRED_SKILL_MD,
    }
)


def _make_context() -> MetaContext:
    return MetaContext(
        archive_index_json="{}",
        archive_skill_summaries_json="[]",
        best_skill_md="",
        recent_feedback_summary_json="{}",
        design_goal="",
    )


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self._iter = iter(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return next(self._iter)


def _make_reflector(tmp_path, responses: list[str]) -> Reflector:
    (tmp_path / "meta_system.md").write_text("You are the meta-agent.")
    (tmp_path / "meta_reflect.md").write_text("Reflect on: CANDIDATE_JSON")
    return Reflector(client=_FakeClient(responses), prompt_dir=str(tmp_path))


class TestReflectorAcceptPath:
    def test_returns_reflection_result(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_ACCEPT_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert isinstance(result, ReflectionResult)

    def test_accept_verdict(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_ACCEPT_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.verdict == "accept"

    def test_empty_issues_on_accept(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_ACCEPT_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.issues == []

    def test_candidate_name_preserved_on_accept(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_ACCEPT_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.candidate.name == "my-skill"

    def test_checks_populated(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_ACCEPT_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.checks.get("json_contract") is True


class TestReflectorRevisePath:
    def test_revise_verdict(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_REVISE_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.verdict == "revise"

    def test_issues_populated(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_REVISE_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert len(result.issues) > 0
        assert "novelty" in result.issues[0].lower()

    def test_repaired_candidate_returned(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_REVISE_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.candidate.name == "my-skill-v2"

    def test_repaired_skill_md_returned(self, tmp_path):
        reflector = _make_reflector(tmp_path, [_REVISE_RESPONSE])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert "my-skill-v2" in result.candidate.skill_md


class TestReflectorPromptBuilding:
    def test_candidate_json_in_user_prompt(self, tmp_path):
        client = _FakeClient([_ACCEPT_RESPONSE])
        (tmp_path / "meta_system.md").write_text("system")
        (tmp_path / "meta_reflect.md").write_text("Reflect: CANDIDATE_JSON")
        reflector = Reflector(client=client, prompt_dir=str(tmp_path))
        reflector.reflect(_CANDIDATE, _make_context())

        _, user_prompt = client.calls[0]
        assert _CANDIDATE.name in user_prompt

    def test_unknown_verdict_defaults_to_revise(self, tmp_path):
        response = json.dumps(
            {
                "verdict": "something-weird",
                "issues": [],
                "checks": {},
                "thought": "hmm",
                "name": "x",
                "skill_md": _SKILL_MD,
            }
        )
        reflector = _make_reflector(tmp_path, [response])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.verdict == "revise"

    def test_missing_verdict_defaults_to_revise(self, tmp_path):
        response = json.dumps(
            {"issues": [], "checks": {}, "thought": "hmm", "name": "x", "skill_md": _SKILL_MD}
        )
        reflector = _make_reflector(tmp_path, [response])
        result = reflector.reflect(_CANDIDATE, _make_context())
        assert result.verdict == "revise"

    def test_original_candidate_used_as_fallback_when_fields_missing(self, tmp_path):
        response = json.dumps({"verdict": "accept", "issues": [], "checks": {}, "thought": "ok"})
        reflector = _make_reflector(tmp_path, [response])
        result = reflector.reflect(_CANDIDATE, _make_context())
        # Falls back to original candidate name/skill_md
        assert result.candidate.name == _CANDIDATE.name
        assert result.candidate.skill_md == _CANDIDATE.skill_md
