import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SEARCH_QUERIES = [
    "AI startup 2026",
    "artificial intelligence entrepreneurship",
    "AI founder interview",
    "machine learning startup building",
    "AI product launch",
]
MAX_RESULTS_PER_QUERY = 10
VIDEO_WINDOW_DAYS = 7
TRANSCRIPT_ENABLED = True

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

INFERENCE_BACKEND = os.environ.get("INFERENCE_BACKEND", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "nemotron-super")
_BACKEND_URLS = {
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm":   "http://127.0.0.1:8001/v1",
}
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", _BACKEND_URLS[INFERENCE_BACKEND])

# --- Evaluation scoring weights (must sum to 1.0) ---
SCORE_WEIGHTS = {
    "relevance": 0.25,
    "substance": 0.25,
    "freshness": 0.15,
    "diversity": 0.15,
    "reasoning": 0.10,
    "alignment": 0.10,
}

# --- ADAS meta-agent loop ---
ITERATIONS_PER_NIGHT = 5
MAX_REFLECT_ROUNDS = 2
MAX_DEBUG_RETRIES = 3

# --- Paths (relative to the workspace root == EvoClaw/) ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAS_DIR = os.path.join(BASE_DIR, "adas")
ARCHIVE_DIR = os.path.join(ADAS_DIR, "archive")
ARCHIVE_INDEX = os.path.join(ARCHIVE_DIR, "index.json")
BASELINES_DIR = os.path.join(ADAS_DIR, "baselines")
TEST_SETS_DIR = os.path.join(ADAS_DIR, "test_sets")
PROMPTS_DIR = os.path.join(ADAS_DIR, "prompts")
SKILL_PRODUCTION = os.path.join(BASE_DIR, "skills", "youtube-curator", "SKILL.md")
FEEDBACK_FILE = os.path.join(TEST_SETS_DIR, "feedback.json")

# --- YouTube API quota budget ---
DAILY_SEARCH_BUDGET = 50          # each search = 100 quota units
DAILY_VIDEO_DETAIL_BUDGET = 500   # each video detail = 1 quota unit
