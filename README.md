# EvoClaw

EvoClaw is an **ADAS-style, self-improving YouTube curator** for AI and entrepreneurship content. The target system runs inside a NemoClaw/OpenClaw environment, fetches candidate videos, evaluates curation strategies, evolves better `SKILL.md` prompts over time, and eventually delivers a daily top-3 digest to Telegram.

The repository is currently at the **working fetcher + evaluator + baseline comparison stage**:

- a YouTube fetcher with caching, `subscriber_count` enrichment, and best-effort transcript support
- a modular evaluator stack with DTO models, request loading, algorithmic scoring, optional LLM judging, and weighted aggregation
- a Python adapter that executes the current baseline `SKILL.md` strategies over cached videos
- a Step 5 comparison flow that evaluates all baselines against one cache and persists detailed results
- lazy default LLM-judge initialization so evaluator construction does not require model client setup unless semantic judging is enabled
- evaluator and comparison CLIs with safer defaults: evaluator runs a real scoring flow by default, and baseline comparison fails fast when the required cache file is missing
- typed shared configuration for search, inference, paths, and scoring weights
- three hand-written baseline skills plus a production `SKILL.md` placeholder
- a cron configuration stub for future automation
- a focused pytest suite covering the evaluator path and Step 5 orchestration (**142 tests currently passing**)

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
│   ├── algorithmic_scorer.py     # Deterministic evaluator dimensions
│   ├── archive/                  # Archive index and future generated skills
│   ├── baseline_catalog.py       # Ordered baseline skill discovery
│   ├── baseline_comparison.py    # Step 5 comparison orchestration and CLI
│   ├── baseline_evaluation_models.py # Step 5 DTO-style result contracts
│   ├── baseline_evaluation_runner.py # Multi-skill evaluation orchestration
│   ├── baseline_results/         # Saved Step 5 comparison outputs
│   ├── baselines/                # Seed curation strategies
│   ├── config.py                 # Shared configuration
│   ├── evaluation_result_store.py # Step 5 result persistence
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
├── tests/                        # Unit tests for evaluator and Step 5 flow
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
- `adas/baseline_catalog.py` baseline file discovery
- `adas/baseline_evaluation_models.py` Step 5 result DTOs
- `adas/baseline_evaluation_runner.py` baseline evaluation orchestration
- `adas/evaluation_result_store.py` Step 5 persistence layer
- `adas/baseline_comparison.py` Step 5 comparison service and CLI
- `adas/prompts/eval_judge.md`
- `adas/baselines/*.md`
- `adas/baseline_results/video_cache_w1/summary.json`
- `skills/youtube-curator/SKILL.md`
- `cron/jobs.json`
- local Step 1 validation: real fetch works and produces a reusable cache in `adas/test_sets/video_cache_w1.json`
- evaluator architecture cleanup: smaller modules, DTO separation, injected collaborators, and readability-focused helpers
- baseline comparison results saved under `adas/baseline_results/video_cache_w1/`
- pytest coverage for evaluator, loader, scorer, executor, and Step 5 comparison modules, including evaluator CLI helpers

Current baseline comparison snapshot on `video_cache_w1.json`:

- `recency-first`: **7.3924**
- `engagement-velocity`: **7.1419**
- `llm-substance-judge`: **5.7784**

Current next milestone:

- define the archive entry structure
- start persisting evaluated skills into the archive layer
- carry the Step 5 comparison outputs forward into Step 6

Planned but not yet implemented:

- real OpenClaw execution
- `adas/meta_agent.py`
- meta-agent prompts
- generated archive entries under `adas/archive/skill_*`
- Telegram reaction capture
- automated best-skill deployment
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
- lazy default `LLMJudge` creation only when LLM judging is requested
- weighted aggregation
- algorithmic scoring for `freshness`, `diversity`, and a placeholder `alignment` score
- stricter typed scoring inputs in `adas/algorithmic_scorer.py`
- clearer evaluator orchestration through smaller internal helper methods
- opt-in LLM judging for `relevance`, `substance`, and `reasoning`
- CLI behavior that returns a real scored result even without explicit `--selected-ids`

It does **not** yet run real OpenClaw execution.

Example evaluator run:

```bash
cd adas
python3 evaluator.py --skill baselines/baseline_popular.md --cache video_cache_w1.json
```

Run the full baseline comparison:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/baseline_comparison.py --cache adas/test_sets/video_cache_w1.json
```

This writes:

- per-baseline result files under `adas/baseline_results/video_cache_w1/results/`
- a ranking summary in `adas/baseline_results/video_cache_w1/summary.json`

The comparison service now validates the required cache input up front and keeps feedback loading optional.

## Security and repo hygiene

- `.env` is intentionally ignored and should never be committed.
- generated caches and feedback data in `adas/test_sets/` are ignored
- local archive run outputs under `adas/archive/skill_*/` are ignored
- `.env.example` is the safe template for sharing config shape without secrets

## References

- `Plan.md` describes the full intended design, phases, and success metrics.
- `adas/README.md` documents the ADAS workspace in more detail.
- `ARCHITECTURE.md` explains the current module layout, including Step 5 comparison modules.
- `WORKFLOW.md` explains the runnable fetch -> evaluate -> compare flow.
- `skills/youtube-curator/README.md` explains the production skill directory.
- `cron/README.md` explains the planned scheduler wiring.
