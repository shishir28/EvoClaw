"""End-to-end loop tests with stubbed generator/reflector/evaluator/archive."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adas.meta.models import Candidate, CycleResult, MetaContext, ReflectionResult
from adas.meta.loop import run_cycle

_SKILL_MD = (
    "---\n"
    "name: loop-test-skill\n"
    'version: "1.0"\n'
    "strategy: recency\n"
    "description: Test skill for loop integration tests.\n"
    "author: adas-meta\n"
    "score: null\n"
    "---\n"
    "\n"
    "## Goal\n"
    "Pick fresh AI startup videos for founders.\n"
    "\n"
    "## Steps\n"
    "1. Filter by recency.\n"
    "2. Select top 3 by published_at.\n"
    "\n"
    "## Fallback\n"
    "Use 7-day window if fewer than 3 fresh videos found.\n"
    "\n"
    "Telegram: List top 3 picks with title, channel, and a one-line reason.\n"
)

_CANDIDATE = Candidate(thought="good design", name="loop-test-skill", skill_md=_SKILL_MD)
_ACCEPT = ReflectionResult(
    verdict="accept", issues=[], checks={}, thought="looks good", candidate=_CANDIDATE
)


def _make_context() -> MetaContext:
    return MetaContext(
        archive_index_json='{"best_skill_id": null, "best_score": 0.0, "skills": []}',
        archive_skill_summaries_json="[]",
        best_skill_md="",
        recent_feedback_summary_json="{}",
        design_goal="",
    )


def _make_eval_result(score: float = 7.5) -> MagicMock:
    result = MagicMock()
    result.total_score = score
    result.status = "scored"
    return result


def _make_archive_result(temp_path_str: str, skill_id: str = "skill_001") -> dict:
    return {
        "best_skill_id": skill_id,
        "best_score": 7.5,
        "skills": [
            {
                "skill_id": skill_id,
                "source_type": "meta-agent",
                "origin_skill_path": str(Path(temp_path_str).resolve()),
                "status": "scored",
                "total_score": 7.5,
            }
        ],
    }


class TestSuccessCycle:
    def test_outcome_is_success(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE

        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT

        ev = MagicMock()
        ev.score.return_value = _make_eval_result(7.5)

        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        assert result.outcome == "success"

    def test_eval_result_attached(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        ev.score.return_value = _make_eval_result(8.0)
        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        assert result.eval_result is not None
        assert result.eval_result.total_score == 8.0

    def test_all_stages_called_once(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        ev.score.return_value = _make_eval_result()
        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path
        )

        run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        gen.generate.assert_called_once()
        ref.reflect.assert_called_once()
        ev.score.assert_called_once()
        archive_svc.archive_records.assert_called_once()

    def test_candidate_attached(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        ev.score.return_value = _make_eval_result()
        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        assert result.candidate is not None
        assert result.candidate.name == "loop-test-skill"


class TestDedupeSkipCycle:
    def test_outcome_is_dedupe(self, tmp_path):
        archive_dir = tmp_path / "archive"
        skill_dir = archive_dir / "skill_001"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_SKILL_MD)

        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        archive_svc = MagicMock()

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(archive_dir),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        assert result.outcome == "dedupe"

    def test_evaluate_and_archive_not_called_on_dedupe(self, tmp_path):
        archive_dir = tmp_path / "archive"
        skill_dir = archive_dir / "skill_001"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_SKILL_MD)

        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        archive_svc = MagicMock()

        run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(archive_dir),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        ev.score.assert_not_called()
        archive_svc.archive_records.assert_not_called()


class TestParseFailureCycle:
    def test_generate_raises_returns_parse_failure(self, tmp_path):
        gen = MagicMock()
        gen.generate.side_effect = ValueError("bad JSON from LLM")

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=MagicMock(),
            evaluator=MagicMock(),
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "parse_failure"
        assert "bad JSON" in (result.error or "")

    def test_reflect_raises_returns_parse_failure(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.side_effect = ValueError("reflect JSON broken")

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=MagicMock(),
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "parse_failure"


class TestReflectExhaustedCycle:
    def _revise_result(self) -> ReflectionResult:
        return ReflectionResult(
            verdict="revise",
            issues=["not novel enough"],
            checks={"novelty": False},
            thought="still needs work",
            candidate=_CANDIDATE,
        )

    def test_outcome_is_reflect_exhausted(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = self._revise_result()

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=MagicMock(),
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "reflect_exhausted"

    def test_reflect_called_exactly_max_passes(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = self._revise_result()

        run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=3,
            generator=gen,
            reflector=ref,
            evaluator=MagicMock(),
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert ref.reflect.call_count == 3

    def test_each_reflection_receives_latest_candidate(self, tmp_path):
        revised_once = Candidate(
            thought="revise once",
            name="loop-test-skill-v2",
            skill_md=_SKILL_MD.replace("name: loop-test-skill", "name: loop-test-skill-v2"),
        )
        revised_twice = Candidate(
            thought="revise twice",
            name="loop-test-skill-v3",
            skill_md=_SKILL_MD.replace("name: loop-test-skill", "name: loop-test-skill-v3"),
        )
        reflections = [
            ReflectionResult(
                verdict="revise",
                issues=["first"],
                checks={},
                thought="first repair",
                candidate=revised_once,
            ),
            ReflectionResult(
                verdict="accept",
                issues=[],
                checks={},
                thought="accepted",
                candidate=revised_twice,
            ),
        ]

        seen_candidates: list[Candidate] = []

        def _reflect(candidate, _context):
            seen_candidates.append(candidate)
            return reflections[len(seen_candidates) - 1]

        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.side_effect = _reflect
        ev = MagicMock()
        ev.score.return_value = _make_eval_result()
        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        assert result.outcome == "success"
        assert seen_candidates == [_CANDIDATE, revised_once]

    def test_evaluate_not_called_on_reflect_exhausted(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = self._revise_result()
        ev = MagicMock()

        run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=2,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=MagicMock(),
            context=_make_context(),
        )

        ev.score.assert_not_called()


class TestInvalidReflectPasses:
    def test_negative_reflect_passes_raises(self, tmp_path):
        import pytest
        with pytest.raises(ValueError, match="reflect_passes"):
            run_cycle(
                cache_path=str(tmp_path / "cache.json"),
                archive_dir=str(tmp_path / "archive"),
                feedback_path=str(tmp_path / "feedback.json"),
                temp_dir=str(tmp_path / "tmp"),
                reflect_passes=-1,
                generator=MagicMock(),
                reflector=MagicMock(),
                evaluator=MagicMock(),
                archive_service=MagicMock(),
                context=_make_context(),
            )


class TestEvalErrorCycle:
    def test_evaluator_raises_returns_eval_error(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        ev.score.side_effect = RuntimeError("evaluator crashed")

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "eval_error"
        assert "evaluator crashed" in (result.error or "")


class TestCandidateValidationCycle:
    def test_invalid_frontmatter_returns_parse_failure(self, tmp_path):
        bad_candidate = Candidate(
            thought="bad author",
            name="loop-test-skill",
            skill_md=_SKILL_MD.replace("author: adas-meta", "author: human"),
        )
        gen = MagicMock()
        gen.generate.return_value = bad_candidate
        ref = MagicMock()
        ref.reflect.return_value = ReflectionResult(
            verdict="accept",
            issues=[],
            checks={},
            thought="accepted",
            candidate=bad_candidate,
        )
        ev = MagicMock()

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "parse_failure"
        assert "adas-meta" in (result.error or "")
        ev.score.assert_not_called()

    def test_mismatched_name_returns_parse_failure(self, tmp_path):
        mismatched = Candidate(
            thought="mismatch",
            name="different-name",
            skill_md=_SKILL_MD,
        )
        gen = MagicMock()
        gen.generate.return_value = mismatched
        ref = MagicMock()
        ref.reflect.return_value = ReflectionResult(
            verdict="accept",
            issues=[],
            checks={},
            thought="accepted",
            candidate=mismatched,
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=MagicMock(),
            archive_service=MagicMock(),
            context=_make_context(),
        )

        assert result.outcome == "parse_failure"
        assert "Candidate name must match" in (result.error or "")


class TestCycleResultToDict:
    def test_success_dict_shape(self, tmp_path):
        gen = MagicMock()
        gen.generate.return_value = _CANDIDATE
        ref = MagicMock()
        ref.reflect.return_value = _ACCEPT
        ev = MagicMock()
        ev.score.return_value = _make_eval_result(6.5)
        archive_svc = MagicMock()
        archive_svc.archive_records.side_effect = lambda records, **kw: _make_archive_result(
            records[0].skill_path, "skill_042"
        )

        result = run_cycle(
            cache_path=str(tmp_path / "cache.json"),
            archive_dir=str(tmp_path / "archive"),
            feedback_path=str(tmp_path / "feedback.json"),
            temp_dir=str(tmp_path / "tmp"),
            reflect_passes=1,
            generator=gen,
            reflector=ref,
            evaluator=ev,
            archive_service=archive_svc,
            context=_make_context(),
        )

        d = result.to_dict()
        assert d["outcome"] == "success"
        assert d["candidate_name"] == "loop-test-skill"
        assert d["total_score"] == 6.5
        assert d["skill_id"] == "skill_042"
        assert d["error"] is None

    def test_failure_dict_shape(self):
        result = CycleResult(outcome="parse_failure", error="oops")
        d = result.to_dict()
        assert d["outcome"] == "parse_failure"
        assert d["candidate_name"] is None
        assert d["total_score"] is None
        assert d["skill_id"] is None
        assert d["error"] == "oops"
