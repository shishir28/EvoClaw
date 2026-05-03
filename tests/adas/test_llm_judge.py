"""
Tests for adas/llm_judge.py
"""

from __future__ import annotations

from builders import make_request, skill, video
from llm_judge import LLMJudge, _extract_json_object


class _StubPromptLoader:
    def load(self, name: str) -> str:
        return "SELECTED_VIDEOS_JSON"


class _UnusedChatClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("Chat client should not be used in prompt-building tests.")


class TestBuildJudgePrompt:
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


class TestExtractJsonObject:
    def test_prefers_full_response_json_object(self):
        payload = _extract_json_object('{"relevance": {"score": 8, "reason": "ok"}}')
        assert payload == {"relevance": {"score": 8, "reason": "ok"}}

    def test_falls_back_to_embedded_json_object_when_response_has_wrapper_text(self):
        payload = _extract_json_object(
            'Here is the result:\n{"relevance": {"score": 8, "reason": "ok"}}'
        )
        assert payload == {"relevance": {"score": 8, "reason": "ok"}}
