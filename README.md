# EvoClaw

EvoClaw is an **ADAS-style, self-improving YouTube curator** for AI and entrepreneurship content. The target system runs inside a NemoClaw/OpenClaw environment, fetches candidate videos, evaluates curation strategies, evolves better `SKILL.md` prompts over time, and eventually delivers a daily top-3 digest to Telegram.

The repository is currently at the **working fetcher + evaluator stage**:

- a YouTube fetcher with caching, `subscriber_count` enrichment, and best-effort transcript support
- a modular evaluator stack with DTO models, request loading, algorithmic scoring, optional LLM judging, and weighted aggregation
- a Python adapter that executes the current baseline `SKILL.md` strategies over cached videos
- typed shared configuration for search, inference, paths, and scoring weights
- three hand-written baseline skills plus a production `SKILL.md` placeholder
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
├── ARCHITECTURE.md                # High-level codebase structure
├── WORKFLOW.md                    # Current and planned execution flows
├── adas/
│   ├── algorithmic_scorer.py     # Deterministic evaluator dimensions
│   ├── archive/                  # Archive index and future generated skills
│   ├── baselines/                # Seed curation strategies
│   ├── config.py                 # Shared configuration
│   ├── evaluator.py              # Evaluator orchestration
│   ├── evaluator_loader.py       # Skill/cache/feedback loading
│   ├── evaluator_models.py       # DTO-style evaluator contracts
│   ├── llm_judge.py              # Prompt-driven semantic judging
│   ├── prompts/                  # Evaluator prompts
│   ├── skill_executor.py         # Python adapter for baseline skills
│   ├── test_sets/                # Local caches and feedback artifacts
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
- `adas/config.py` with typed settings plus backward-compatible constants
- `adas/evaluator.py` with full evaluator flow, weighted aggregation, and optional LLM judging
- `adas/evaluator_loader.py` for loading skill, cache, and feedback inputs
- `adas/evaluator_models.py` for evaluator DTOs / data contracts
- `adas/algorithmic_scorer.py` for non-LLM evaluator dimensions
- `adas/llm_judge.py` for prompt-driven model judging
- `adas/skill_executor.py` baseline execution adapter
- `adas/prompts/eval_judge.md`
- `adas/baselines/*.md`
- `skills/youtube-curator/SKILL.md`
- `cron/jobs.json`
- local Step 1 validation: real fetch works and produces a reusable cache in `adas/test_sets/video_cache_w1.json`
- evaluator architecture cleanup: smaller modules, DTO separation, injected collaborators, and readability-focused helpers

Current next milestone:

- run all three baselines against the same dataset
- save and compare evaluator result breakdowns
- confirm the scores feel sensible before building the archive and meta-agent loop

Planned but not yet implemented:

- real OpenClaw execution
- `adas/meta_agent.py`
- meta-agent prompts
- generated archive entries under `adas/archive/skill_*`
- Telegram reaction capture
- automated best-skill deployment
- archive result persistence beyond the empty `adas/archive/index.json` stub
- end-to-end cron-driven runtime wiring

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

The evaluator currently supports:

- loading a skill, cache, and optional feedback history
- a separate evaluator loader module for file and request assembly
- `score()` orchestration for explicitly selected cached videos or auto-selected baseline picks
- automatic execution of the current baseline-style skills through a Python adapter
- registry-driven baseline strategy execution for easier extension
- a separate evaluator models module for DTO-style dataclasses
- separated scoring modules for algorithmic logic and LLM judging
- injectable prompt and chat adapters for LLM judging
- weighted aggregation
- algorithmic scoring for `freshness`, `diversity`, and a placeholder `alignment` score
- stricter typed scoring inputs in `adas/algorithmic_scorer.py`
- clearer evaluator orchestration through smaller internal helper methods
- opt-in LLM judging for `relevance`, `substance`, and `reasoning`

It does **not** yet run real OpenClaw execution.

Example evaluator run:

```bash
cd adas
python3 evaluator.py --skill baselines/baseline_popular.md --cache video_cache_w1.json
```

## Security and repo hygiene

- `.env` is intentionally ignored and should never be committed.
- generated caches and feedback data in `adas/test_sets/` are ignored
- local archive run outputs under `adas/archive/skill_*/` are ignored
- `.env.example` is the safe template for sharing config shape without secrets

## References

- `ARCHITECTURE.md` explains the current module boundaries and responsibilities.
- `WORKFLOW.md` explains what you can run today and how the full loop is intended to evolve.
- `Plan.md` describes the full intended design, phases, and success metrics.
- `adas/README.md` documents the ADAS workspace in more detail.
- `skills/youtube-curator/README.md` explains the production skill directory.
- `cron/README.md` explains the planned scheduler wiring.
