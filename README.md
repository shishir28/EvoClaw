# EvoClaw

EvoClaw is a planned **ADAS-style, self-improving YouTube curator** for AI and entrepreneurship content. The target system runs inside a NemoClaw/OpenClaw environment, fetches candidate videos, evaluates curation strategies, evolves better `SKILL.md` prompts over time, and delivers a daily top-3 digest to Telegram.

At the moment, this repository contains the **foundation layer** of that system:

- a YouTube fetcher with caching, `subscriber_count` enrichment, and best-effort transcript support
- three hand-written baseline skills
- shared configuration for search, inference, and scoring weights
- a production `SKILL.md` placeholder
- a cron configuration stub for future automation

## Target architecture

The planned end-to-end loop is:

1. Fetch candidate videos from YouTube.
2. Score candidate curation skills on cached datasets.
3. Use a meta agent to propose improved `SKILL.md` strategies.
4. Archive results and deploy the best-performing skill.
5. Run the production skill on a schedule and send picks to Telegram.
6. Collect feedback and feed it back into evaluation.

## Repository layout

```text
EvoClaw/
├── adas/
│   ├── archive/                  # Archive index and future generated skills
│   ├── baselines/                # Seed curation strategies
│   ├── test_sets/                # Local caches and feedback artifacts
│   ├── config.py                 # Shared configuration
│   └── youtube_fetcher.py        # YouTube data collection and caching
├── cron/
│   ├── README.md
│   └── jobs.json                 # Planned automation schedule
├── skills/
│   └── youtube-curator/
│       ├── README.md
│       └── SKILL.md              # Current production skill placeholder
├── .env.example                  # Environment variable template
├── .gitignore                    # Excludes secrets and generated data
├── Plan.md                       # Original project design and roadmap
├── README.md
└── requirements.txt
```

## Current status

Implemented now:

- `adas/youtube_fetcher.py`
- `adas/config.py`
- `adas/baselines/*.md`
- `skills/youtube-curator/SKILL.md`
- `cron/jobs.json`
- local Step 1 validation: real fetch works and produces a reusable cache in `adas/test_sets/video_cache_w1.json`

Planned but not yet implemented:

- `adas/evaluator.py`
- `adas/meta_agent.py`
- `adas/prompts/`
- generated archive entries under `adas/archive/skill_*`
- Telegram reaction capture
- automated best-skill deployment

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

4. Fill in the required values in `.env`:
   - `YOUTUBE_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - optional inference settings such as `INFERENCE_BACKEND`, `LLM_BASE_URL`, and `LLM_MODEL`

## Usage

Fetch and cache a test set of videos:

```bash
cd adas
python youtube_fetcher.py --days 7 --max-per-query 10 --output video_cache_w1.json
```

This writes the cache into `adas/test_sets/`.

The current fetcher output includes:

- core video metadata
- `views_per_hour`
- `subscriber_count`
- `transcript` when available

Transcript fetching is **best-effort**. Some videos may still have `transcript: null` if YouTube blocks caption retrieval for the current IP.

## Security and repo hygiene

- `.env` is intentionally ignored and should never be committed.
- generated caches and feedback data in `adas/test_sets/` are ignored
- local archive run outputs under `adas/archive/skill_*/` are ignored
- `.env.example` is the safe template for sharing config shape without secrets

## References

- `Plan.md` describes the full intended design, phases, and success metrics.
- `adas/README.md` documents the ADAS workspace in more detail.
- `skills/youtube-curator/README.md` explains the production skill directory.
- `cron/README.md` explains the planned scheduler wiring.
