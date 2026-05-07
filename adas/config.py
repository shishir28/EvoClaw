"""
Application configuration for EvoClaw.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_DEFAULT_BACKEND_URLS = {
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm": "http://127.0.0.1:8001/v1",
}


@dataclass(frozen=True, slots=True)
class SearchSettings:
    queries: tuple[str, ...]
    max_results_per_query: int
    video_window_days: int
    transcript_enabled: bool


@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    youtube_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str


@dataclass(frozen=True, slots=True)
class InferenceSettings:
    backend: str
    model: str
    base_url: str


@dataclass(frozen=True, slots=True)
class EvaluationSettings:
    score_weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class LoopSettings:
    iterations_per_night: int
    max_reflect_rounds: int
    max_debug_retries: int


@dataclass(frozen=True, slots=True)
class PathSettings:
    base_dir: str
    adas_dir: str
    archive_dir: str
    archive_index: str
    baselines_dir: str
    baseline_results_dir: str
    test_sets_dir: str
    prompts_dir: str
    skill_production: str
    skill_delivery_log: str
    feedback_file: str


@dataclass(frozen=True, slots=True)
class QuotaSettings:
    daily_search_budget: int
    daily_video_detail_budget: int


@dataclass(frozen=True, slots=True)
class AppSettings:
    search: SearchSettings
    integrations: IntegrationSettings
    inference: InferenceSettings
    evaluation: EvaluationSettings
    loop: LoopSettings
    paths: PathSettings
    quotas: QuotaSettings


def _load_environment(env_file: Path = DEFAULT_ENV_FILE) -> None:
    if env_file.exists():
        load_dotenv(env_file)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_inference_base_url(backend: str) -> str:
    return os.environ.get(
        "LLM_BASE_URL",
        _DEFAULT_BACKEND_URLS.get(backend, _DEFAULT_BACKEND_URLS["ollama"]),
    )


def _build_search_settings() -> SearchSettings:
    return SearchSettings(
        queries=(
            "AI startup 2026",
            "artificial intelligence entrepreneurship",
            "AI founder interview",
            "machine learning startup building",
            "AI product launch",
        ),
        max_results_per_query=10,
        video_window_days=7,
        transcript_enabled=_bool_env("TRANSCRIPT_ENABLED", True),
    )


def _build_integration_settings() -> IntegrationSettings:
    return IntegrationSettings(
        youtube_api_key=os.environ.get("YOUTUBE_API_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    )


def _build_inference_settings() -> InferenceSettings:
    backend = os.environ.get("INFERENCE_BACKEND", "ollama")
    return InferenceSettings(
        backend=backend,
        model=os.environ.get("LLM_MODEL", "nemotron-super"),
        base_url=_resolve_inference_base_url(backend),
    )


def _build_evaluation_settings() -> EvaluationSettings:
    return EvaluationSettings(
        score_weights={
            "relevance": 0.25,
            "substance": 0.25,
            "freshness": 0.15,
            "diversity": 0.15,
            "reasoning": 0.10,
            "alignment": 0.10,
        }
    )


def _build_loop_settings() -> LoopSettings:
    return LoopSettings(
        iterations_per_night=5,
        max_reflect_rounds=2,
        max_debug_retries=3,
    )


def _build_path_settings(base_dir: Path) -> PathSettings:
    adas_dir = base_dir / "adas"
    archive_dir = adas_dir / "archive"
    test_sets_dir = adas_dir / "test_sets"
    return PathSettings(
        base_dir=str(base_dir),
        adas_dir=str(adas_dir),
        archive_dir=str(archive_dir),
        archive_index=str(archive_dir / "index.json"),
        baselines_dir=str(adas_dir / "baselines"),
        baseline_results_dir=str(adas_dir / "baseline_results"),
        test_sets_dir=str(test_sets_dir),
        prompts_dir=str(adas_dir / "prompts"),
        skill_production=str(base_dir / "skills" / "youtube-curator" / "SKILL.md"),
        skill_delivery_log=str(base_dir / "skills" / "youtube-curator" / "delivery_log.json"),
        feedback_file=str(test_sets_dir / "feedback.json"),
    )


def _build_quota_settings() -> QuotaSettings:
    return QuotaSettings(
        daily_search_budget=50,
        daily_video_detail_budget=500,
    )


def load_settings(env_file: Path = DEFAULT_ENV_FILE) -> AppSettings:
    _load_environment(env_file)

    base_dir = Path(__file__).resolve().parent.parent

    return AppSettings(
        search=_build_search_settings(),
        integrations=_build_integration_settings(),
        inference=_build_inference_settings(),
        evaluation=_build_evaluation_settings(),
        loop=_build_loop_settings(),
        paths=_build_path_settings(base_dir),
        quotas=_build_quota_settings(),
    )


SETTINGS = load_settings()

# Backward-compatible constant exports
SEARCH_QUERIES = list(SETTINGS.search.queries)
MAX_RESULTS_PER_QUERY = SETTINGS.search.max_results_per_query
VIDEO_WINDOW_DAYS = SETTINGS.search.video_window_days
TRANSCRIPT_ENABLED = SETTINGS.search.transcript_enabled

YOUTUBE_API_KEY = SETTINGS.integrations.youtube_api_key
TELEGRAM_BOT_TOKEN = SETTINGS.integrations.telegram_bot_token
TELEGRAM_CHAT_ID = SETTINGS.integrations.telegram_chat_id

INFERENCE_BACKEND = SETTINGS.inference.backend
LLM_MODEL = SETTINGS.inference.model
LLM_BASE_URL = SETTINGS.inference.base_url

SCORE_WEIGHTS = dict(SETTINGS.evaluation.score_weights)

ITERATIONS_PER_NIGHT = SETTINGS.loop.iterations_per_night
MAX_REFLECT_ROUNDS = SETTINGS.loop.max_reflect_rounds
MAX_DEBUG_RETRIES = SETTINGS.loop.max_debug_retries

BASE_DIR = SETTINGS.paths.base_dir
ADAS_DIR = SETTINGS.paths.adas_dir
ARCHIVE_DIR = SETTINGS.paths.archive_dir
ARCHIVE_INDEX = SETTINGS.paths.archive_index
BASELINES_DIR = SETTINGS.paths.baselines_dir
BASELINE_RESULTS_DIR = SETTINGS.paths.baseline_results_dir
TEST_SETS_DIR = SETTINGS.paths.test_sets_dir
PROMPTS_DIR = SETTINGS.paths.prompts_dir
SKILL_PRODUCTION = SETTINGS.paths.skill_production
DELIVERY_LOG = SETTINGS.paths.skill_delivery_log
FEEDBACK_FILE = SETTINGS.paths.feedback_file

DAILY_SEARCH_BUDGET = SETTINGS.quotas.daily_search_budget
DAILY_VIDEO_DETAIL_BUDGET = SETTINGS.quotas.daily_video_detail_budget

# Meta-agent settings (read from environment, not stored in AppSettings)
META_REFLECT_PASSES: int = int(os.environ.get("META_REFLECT_PASSES", "2"))
META_MAX_CYCLES: int = int(os.environ.get("META_MAX_CYCLES", "1"))
META_CANDIDATE_TEMP_DIR: str = os.environ.get(
    "META_CANDIDATE_TEMP_DIR",
    str(Path(__file__).resolve().parent / ".meta_tmp"),
)
