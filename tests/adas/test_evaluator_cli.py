"""
Tests for evaluator CLI helpers and lazy judge initialization.
"""

from __future__ import annotations

from types import SimpleNamespace

import evaluator as evaluator_module
from builders import make_request, make_result, video
from evaluator import Evaluator, _build_cli_output
from skill_executor import SkillExecutionResult


class _StubRequestLoader:
    def __init__(self, request):
        self._request = request

    def load_request(self, skill_path: str, cache_path: str, feedback_path: str | None = None):
        return self._request


class _StubExecutor:
    def execute(self, skill_doc, videos):
        return SkillExecutionResult(
            selected_video_ids=[video.video_id for video in videos[:3]],
            notes=["stub"],
        )


class TestEvaluatorLazyLLMJudge:
    def test_default_llm_judge_is_not_created_when_llm_scoring_is_disabled(self, monkeypatch):
        created: list[str] = []

        class _StubJudge:
            def __init__(self):
                created.append("created")

            def judge_dimensions(self, request, selected_videos):
                return (
                    {"relevance": 8.0, "substance": 8.0, "reasoning": 8.0},
                    {
                        "relevance": "ok",
                        "substance": "ok",
                        "reasoning": "ok",
                    },
                )

        monkeypatch.setattr(evaluator_module, "LLMJudge", _StubJudge)
        request = make_request(
            videos=[video().with_id(f"v{i}").with_channel("Tech", f"ch{i}").build() for i in range(3)]
        )
        evaluator = Evaluator(
            request_loader=_StubRequestLoader(request),
            skill_executor=_StubExecutor(),
        )

        result = evaluator.score("skill.md", "cache.json", use_llm_judging=False)

        assert created == []
        assert result.status == "partially_scored"

    def test_default_llm_judge_is_created_only_when_needed(self, monkeypatch):
        created: list[str] = []

        class _StubJudge:
            def __init__(self):
                created.append("created")

            def judge_dimensions(self, request, selected_videos):
                return (
                    {"relevance": 8.0, "substance": 8.0, "reasoning": 8.0},
                    {
                        "relevance": "ok",
                        "substance": "ok",
                        "reasoning": "ok",
                    },
                )

        monkeypatch.setattr(evaluator_module, "LLMJudge", _StubJudge)
        request = make_request(
            videos=[video().with_id(f"v{i}").with_channel("Tech", f"ch{i}").build() for i in range(3)]
        )
        evaluator = Evaluator(
            request_loader=_StubRequestLoader(request),
            skill_executor=_StubExecutor(),
        )

        result = evaluator.score("skill.md", "cache.json", use_llm_judging=True)

        assert created == ["created"]
        assert result.status == "scored"


class _StubCLIReaderEvaluator:
    def __init__(self, request, result):
        self._request = request
        self._result = result
        self.score_calls: list[dict[str, object]] = []

    def load_request(self, skill_path: str, cache_path: str, feedback_path: str | None = None):
        return self._request

    def score(
        self,
        skill_path: str,
        cache_path: str,
        selected_video_ids: list[str] | None = None,
        feedback_path: str | None = None,
        extra_scores: dict[str, float] | None = None,
        extra_details: dict[str, str] | None = None,
        use_llm_judging: bool = False,
    ):
        self.score_calls.append(
            {
                "skill_path": skill_path,
                "cache_path": cache_path,
                "selected_video_ids": selected_video_ids,
                "feedback_path": feedback_path,
                "extra_scores": extra_scores,
                "extra_details": extra_details,
                "use_llm_judging": use_llm_judging,
            }
        )
        return self._result


class TestBuildCLIOutput:
    def test_always_runs_score_and_returns_result_key(self):
        request = make_request(videos=[video().build()])
        result = make_result()
        result.status = "partially_scored"
        evaluator = _StubCLIReaderEvaluator(request, result)
        args = SimpleNamespace(
            skill="skill.md",
            cache="cache.json",
            feedback="feedback.json",
            selected_ids=None,
            extra_scores_json=None,
            extra_details_json=None,
            with_llm_judge=False,
        )

        payload = _build_cli_output(evaluator, args)

        assert evaluator.score_calls == [
            {
                "skill_path": "skill.md",
                "cache_path": "cache.json",
                "selected_video_ids": None,
                "feedback_path": "feedback.json",
                "extra_scores": None,
                "extra_details": None,
                "use_llm_judging": False,
            }
        ]
        assert "result" in payload
        assert "result_template" not in payload

    def test_parses_cli_selected_ids_and_extra_json(self):
        request = make_request(videos=[video().build()])
        result = make_result(selected_video_ids=["v1", "v2", "v3"])
        evaluator = _StubCLIReaderEvaluator(request, result)
        args = SimpleNamespace(
            skill="skill.md",
            cache="cache.json",
            feedback="feedback.json",
            selected_ids="v1, v2 ,v3",
            extra_scores_json='{"freshness": 8.0}',
            extra_details_json='{"freshness": "manual"}',
            with_llm_judge=True,
        )

        _build_cli_output(evaluator, args)

        assert evaluator.score_calls[0]["selected_video_ids"] == ["v1", "v2", "v3"]
        assert evaluator.score_calls[0]["extra_scores"] == {"freshness": 8.0}
        assert evaluator.score_calls[0]["extra_details"] == {"freshness": "manual"}
        assert evaluator.score_calls[0]["use_llm_judging"] is True
