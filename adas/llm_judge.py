"""
LLM-based judging for evaluator dimensions that require semantic assessment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

try:
    from config import LLM_BASE_URL, LLM_MODEL, PROMPTS_DIR
    from evaluator_models import EvaluationRequest, VideoRecord
except ModuleNotFoundError:
    from adas.config import LLM_BASE_URL, LLM_MODEL, PROMPTS_DIR
    from adas.evaluator_models import EvaluationRequest, VideoRecord


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    match = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)
    return match[0][:240]


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Model response did not contain a valid JSON object.")


class PromptTemplateLoader(Protocol):
    def load(self, name: str) -> str: ...


class ChatCompletionClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class FilePromptTemplateLoader:
    def __init__(self, prompt_dir: str = PROMPTS_DIR) -> None:
        self._prompt_dir = Path(prompt_dir)

    def load(self, name: str) -> str:
        return (self._prompt_dir / name).read_text()


class OpenAIChatCompletionClient:
    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The 'openai' package is required for LLM judging.") from exc
        self._client = OpenAI(api_key="local", base_url=base_url)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            from openai import APIConnectionError, APIStatusError, APITimeoutError
        except ImportError as exc:
            raise RuntimeError("The 'openai' package is required for LLM judging.") from exc

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except (APIConnectionError, APIStatusError, APITimeoutError) as exc:
            raise RuntimeError(f"LLM judging request failed: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise RuntimeError("LLM judging returned no message content.")
        return content


class LLMJudge:
    def __init__(
        self,
        prompt_loader: PromptTemplateLoader | None = None,
        chat_client: ChatCompletionClient | None = None,
        prompt_dir: str = PROMPTS_DIR,
        base_url: str = LLM_BASE_URL,
        model: str = LLM_MODEL,
    ) -> None:
        self._prompt_loader = prompt_loader or FilePromptTemplateLoader(prompt_dir)
        self._chat_client = chat_client or OpenAIChatCompletionClient(base_url, model)

    def _build_reasoning_summaries(
        self,
        request: EvaluationRequest,
        selected_videos: list[VideoRecord],
    ) -> dict[str, str]:
        summaries: dict[str, str] = {}
        for video in selected_videos:
            desc = _first_sentence(video.transcript_or_description)
            if request.skill.strategy == "recency":
                summaries[video.video_id] = (
                    desc
                    or "Recent AI/startup video selected because it is among the newest relevant matches."
                )
            elif request.skill.strategy == "engagement-velocity":
                summaries[video.video_id] = (
                    desc
                    or "High-velocity AI/startup video selected for unusually strong recent attention."
                )
            elif request.skill.strategy == "llm-substance-judge":
                summaries[video.video_id] = (
                    desc
                    or "Potentially substantive AI/startup video selected for richer content signals."
                )
            else:
                summaries[video.video_id] = (
                    desc
                    or "Selected AI/startup video chosen by the current evaluator execution path."
                )
        return summaries

    def _build_judge_prompt(
        self,
        request: EvaluationRequest,
        selected_videos: list[VideoRecord],
    ) -> str:
        prompt_template = self._prompt_loader.load("eval_judge.md")
        reasoning_summaries = self._build_reasoning_summaries(request, selected_videos)
        selected_payload = [
            {
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel,
                "published_at": video.published_at,
                "views": video.views,
                "subscriber_count": video.subscriber_count,
                "views_per_hour": video.views_per_hour,
                "description": video.description,
                "transcript_excerpt": (video.transcript_or_description or "")[:1500],
                "why_watch_summary": reasoning_summaries[video.video_id],
            }
            for video in selected_videos
        ]
        return (
            prompt_template
            .replace("SKILL_NAME", request.skill.name or Path(request.skill.path).stem)
            .replace("SKILL_STRATEGY", request.skill.strategy or "unknown")
            .replace("SKILL_DESCRIPTION", request.skill.description or "")
            .replace("SELECTED_VIDEOS_JSON", json.dumps(selected_payload, indent=2, ensure_ascii=False))
        )

    def judge_dimensions(
        self,
        request: EvaluationRequest,
        selected_videos: list[VideoRecord],
    ) -> tuple[dict[str, float], dict[str, str]]:
        prompt = self._build_judge_prompt(request, selected_videos)
        content = self._chat_client.complete(
            system_prompt="You are a strict evaluation judge. Return JSON only.",
            user_prompt=prompt,
        )
        parsed = _extract_json_object(content)
        scores: dict[str, float] = {}
        details: dict[str, str] = {}
        for name in ("relevance", "substance", "reasoning"):
            if name not in parsed or not isinstance(parsed[name], dict):
                raise ValueError(f"LLM judge response is missing '{name}'.")
            item = parsed[name]
            if "score" not in item or "reason" not in item:
                raise ValueError(f"LLM judge response for '{name}' must include score and reason.")
            score = float(item["score"])
            if not 0.0 <= score <= 10.0:
                raise ValueError(f"LLM judge score for '{name}' must be between 0 and 10.")
            scores[name] = score
            details[name] = str(item["reason"]).strip()

        return scores, details
