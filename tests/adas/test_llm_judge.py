"""
Tests for adas/llm_judge.py
"""

from __future__ import annotations

from builders import make_request, skill, video
import adas.evaluation.judge as judge_module
from adas.evaluation.judge import LLMJudge, _extract_json_object


class _StubPromptLoader:
    def load(self, name: str) -> str:
        return "SELECTED_VIDEOS_JSON"


class _UnusedChatClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("Chat client should not be used in prompt-building tests.")


class TestBuildJudgePrompt:
    def test_default_chat_client_is_not_created_until_judging_runs(self, monkeypatch):
        created: list[str] = []

        class _StubChatClient:
            def __init__(self) -> None:
                created.append("created")

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return (
                    '{"relevance": {"score": 8, "reason": "ok"}, '
                    '"substance": {"score": 8, "reason": "ok"}, '
                    '"reasoning": {"score": 8, "reason": "ok"}}'
                )

        monkeypatch.setattr(judge_module, "OpenAIChatCompletionClient", _StubChatClient)
        judge = LLMJudge(prompt_loader=_StubPromptLoader())
        request = make_request(
            skill_doc=skill().with_name("baseline").with_strategy("llm-substance-judge").build(),
            videos=[],
        )
        selected_videos = [video().with_id("v1").build()]

        judge._build_judge_prompt(request, selected_videos)

        assert created == []

    def test_prompt_includes_transcript_source_metadata(self):
        judge = LLMJudge(prompt_loader=_StubPromptLoader(), chat_client=_UnusedChatClient())
        request = make_request(
            skill_doc=skill().with_name("baseline").with_strategy("llm-substance-judge").build(),
            videos=[],
        )
        selected_videos = [
            video()
            .with_id("with-transcript")
            .with_description("Description only.")
            .with_transcript("Transcript text.")
            .build(),
            video()
            .with_id("with-description")
            .with_description("Description fallback.")
            .with_transcript(None)
            .build(),
        ]

        prompt = judge._build_judge_prompt(request, selected_videos)

        assert '"video_id": "with-transcript"' in prompt
        assert '"has_transcript": true' in prompt
        assert '"content_source": "transcript"' in prompt
        assert '"video_id": "with-description"' in prompt
        assert '"has_transcript": false' in prompt
        assert '"content_source": "description"' in prompt

    def test_default_chat_client_is_created_when_judging_runs(self, monkeypatch):
        created: list[str] = []

        class _StubChatClient:
            def __init__(self, base_url: str, model: str) -> None:
                created.append(f"{base_url}:{model}")

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return (
                    '{"relevance": {"score": 8, "reason": "ok"}, '
                    '"substance": {"score": 8, "reason": "ok"}, '
                    '"reasoning": {"score": 8, "reason": "ok"}}'
                )

        monkeypatch.setattr(judge_module, "OpenAIChatCompletionClient", _StubChatClient)
        judge = LLMJudge(prompt_loader=_StubPromptLoader())
        request = make_request(
            skill_doc=skill().with_name("baseline").with_strategy("llm-substance-judge").build(),
            videos=[],
        )
        selected_videos = [video().with_id("v1").build()]

        scores, details = judge.judge_dimensions(request, selected_videos)

        assert created == [f"{judge_module.LLM_BASE_URL}:{judge_module.LLM_MODEL}"]
        assert scores == {"relevance": 8.0, "substance": 8.0, "reasoning": 8.0}
        assert details == {"relevance": "ok", "substance": "ok", "reasoning": "ok"}


class TestExtractJsonObject:
    def test_prefers_full_response_json_object(self):
        payload = _extract_json_object('{"relevance": {"score": 8, "reason": "ok"}}')
        assert payload == {"relevance": {"score": 8, "reason": "ok"}}

    def test_falls_back_to_embedded_json_object_when_response_has_wrapper_text(self):
        payload = _extract_json_object(
            'Here is the result:\n{"relevance": {"score": 8, "reason": "ok"}}'
        )
        assert payload == {"relevance": {"score": 8, "reason": "ok"}}
