# EvoClaw

EvoClaw is an **ADAS-style, self-improving YouTube curator** for AI and entrepreneurship content. It fetches YouTube candidates, evaluates curation strategies, evolves better `SKILL.md` prompts, promotes the best skill, sends daily Telegram video picks, and captures Telegram reactions as feedback.

The repository currently includes:

- a YouTube fetcher with caching, `subscriber_count` enrichment, and best-effort transcript support
- a modular evaluator stack with DTO models, request loading, algorithmic scoring, optional LLM judging, and weighted aggregation
- a Python adapter that executes the current baseline `SKILL.md` strategies over cached videos
- a baseline comparison flow that evaluates all baselines against one cache and persists detailed results
- an archive flow that writes `SKILL.md`, `result.json`, `meta.json`, and best-skill metadata under `adas/archive/`
- a feedback flow that validates reactions, persists video snapshots atomically, and turns `alignment` into a heuristic preference signal
- a meta-agent flow that builds prompt context, generates a candidate skill, runs reflection passes, validates the candidate locally, evaluates it, and archives successful runs
- a skill promoter that copies the archive winner into `skills/youtube-curator/SKILL.md` only when it beats the recorded production deployment
- a Telegram delivery flow that runs the promoted production skill, sends one Telegram message per selected video, and records per-video message metadata in `delivery_log.json`
- a Telegram reaction capture flow that polls for reactions, maps each reaction back to the specific delivered video, and writes `FeedbackEntry` records to `feedback.json`
- lazy default LLM-judge initialization so evaluator construction does not require model client setup unless semantic judging is enabled
- typed shared configuration for search, inference, paths, and scoring weights
- three hand-written baseline skills plus a production `SKILL.md` target
- a job runner that executes schedules defined in `cron/jobs.json`
- a focused pytest suite covering evaluator, archive, feedback, Telegram, and scheduler behavior

## Runtime loop

The scheduled loop is defined in `cron/jobs.json` and is driven externally by NemoClaw/OpenShell:

1. Refresh the reusable YouTube cache at 00:30.
2. Run the ADAS evolution loop at 01:30.
3. Send the daily Telegram picks at 04:30.
4. Capture Telegram reactions at 08:30.
5. Feed captured reactions into future alignment scoring.

## Repository layout

```text
EvoClaw/
|-- adas/
|   |-- archive/                  # Versioned archive entries and best-skill index
|   |-- archive_runtime/          # Archive models, store, and service
|   |-- baseline/                 # Baseline comparison internals
|   |-- baseline_results/         # Saved comparison outputs
|   |-- baselines/                # Seed curation strategies
|   |-- config.py                 # Shared configuration
|   |-- deployment/               # Production skill promotion
|   |-- evaluation/               # Evaluator models, loader, scorer, judge, executor, service
|   |-- feedback/                 # Feedback store and append service
|   |-- meta/                     # Meta-agent context, generation, reflection, parsing
|   |-- telegram/                 # Telegram delivery, reaction polling, and feedback capture
|   |-- baseline_comparison.py    # CLI entrypoint and compatibility wrapper
|   |-- evaluator.py              # CLI entrypoint and compatibility wrapper
|   |-- feedback_cli.py           # Manual feedback append CLI
|   |-- meta_agent.py             # Meta-agent CLI entrypoint
|   |-- telegram_digest.py        # Telegram digest CLI
|   |-- telegram_feedback.py      # Telegram reaction feedback capture CLI
|   |-- prompts/                  # Evaluator and meta-agent prompts
|   |-- test_sets/                # Local caches and feedback artifacts
|   `-- youtube_fetcher.py        # YouTube data collection and caching
|-- cron/
|   |-- README.md
|   `-- jobs.json                 # Canonical automation schedule
|-- skills/
|   `-- youtube-curator/
|       |-- README.md
|       `-- SKILL.md              # Current production skill target
|-- .env.example                  # Environment variable template
|-- .gitignore                    # Excludes secrets and generated data
|-- docs/
|   `-- history/                  # Original design plan and implementation checklist (historical)
|-- README.md
|-- tests/                        # Unit tests for evaluator, runtime, Telegram, and cron paths
`-- requirements.txt
```

## Current status

Main implemented pieces:

- `adas/youtube_fetcher.py`
- `adas/config.py` with typed settings plus backward-compatible constants
- `adas/evaluation/` for evaluator internals grouped by domain
- `adas/baseline/` for baseline comparison internals grouped by domain
- `adas/archive_runtime/` for archive internals grouped by domain
- `adas/feedback/` for feedback persistence and append logic
- `adas/meta/` for meta-agent orchestration internals
- `adas/deployment/` for production skill promotion
- `adas/telegram/` for digest formatting, per-video sending, delivery metadata logging, reaction polling, and feedback capture
- top-level CLI entrypoints for evaluator, baseline comparison, feedback append, meta-agent, digest delivery, and reaction capture
- `adas/prompts/` evaluator and meta-agent prompts
- `adas/baselines/*.md`
- `adas/baseline_results/` comparison outputs
- `adas/archive/index.json` and versioned archive entries
- `skills/youtube-curator/SKILL.md`
- `skills/youtube-curator/delivery_log.json` after the first delivery run
- `cron/jobs.json` as the canonical schedule source
- atomic persistence for feedback and delivery-log writes

Known limitations:

- real OpenClaw execution is still represented by the Python adapter
- generated candidate archive entries beyond the seeded baselines depend on a reachable OpenAI-compatible LLM endpoint

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

### Docker with bundled vLLM

`docker-compose.yml` can run EvoClaw and a sibling `vllm-evo` container on the
same Docker network. By default:

- `vllm-evo` serves `${EVOCLAW_VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}`
- EvoClaw points `LLM_BASE_URL` at `http://vllm-evo:8000/v1`
- the vLLM API is also published to the host on `${EVOCLAW_VLLM_PORT:-9001}`

Bring the stack up with:

```bash
docker compose up -d --build
```

If you want EvoClaw to keep using some other endpoint, override
`EVOCLAW_LLM_BASE_URL` or `LLM_BASE_URL` in `.env`.

### External scheduler

EvoClaw does not install its own cron scheduler. The daily jobs are launched by
NemoClaw/OpenShell using the schedule in `cron/jobs.json`. The job runner still
executes inside the EvoClaw codebase, but scheduling is owned by the gateway
layer.

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

Transcript fetching is **best-effort**. Some videos may still have `transcript: null` if YouTube blocks caption retrieval for the current IP. The selector still filters non-English candidates using YouTube language metadata plus title/description/tag heuristics, so the digest does not depend on transcripts being available.

If the current IP is blocked, configure a residential or rotating proxy through `.env` and restart EvoClaw or the gateway service:

```bash
TRANSCRIPT_PROXY_HTTP_URL=http://user:pass@proxy-host:port
TRANSCRIPT_PROXY_HTTPS_URL=http://user:pass@proxy-host:port
```

For Webshare residential proxies, use:

```bash
TRANSCRIPT_WEBSHARE_USERNAME=your-webshare-username
TRANSCRIPT_WEBSHARE_PASSWORD=your-webshare-password
TRANSCRIPT_WEBSHARE_LOCATIONS=AU,US
TRANSCRIPT_PROXY_RETRIES_WHEN_BLOCKED=10
```

Cookie-based transcript auth is not wired because the installed `youtube-transcript-api` version has cookie support disabled internally; proxy support is the supported path here.

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
- algorithmic scoring for `freshness`, `diversity`, and a feedback-driven `alignment` score
- stricter typed scoring inputs in `adas/evaluation/scorer.py`
- clearer evaluator orchestration through smaller internal helper methods
- opt-in LLM judging for `relevance`, `substance`, and `reasoning`
- CLI behavior that returns a real scored result even without explicit `--selected-ids`

Internally, those evaluator concerns now live under `adas/evaluation/`.

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

Archive those evaluated skills into Step 6:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/baseline_comparison.py --cache adas/test_sets/video_cache_w1.json --archive
```

This additionally writes:

- `adas/archive/index.json`
- `adas/archive/skill_###/SKILL.md`
- `adas/archive/skill_###/result.json`
- `adas/archive/skill_###/meta.json`

Run the Step 9 meta-agent:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/meta_agent.py --cache adas/test_sets/video_cache_w1.json --reflect-passes 2
```

Run the Step 9 loop and promote the archive winner when it beats production:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/meta_agent.py --cache adas/test_sets/video_cache_w1.json --reflect-passes 2 --deploy-best
```

Run the Step 11 digest flow in dry-run mode:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/telegram_digest.py --cache adas/test_sets/video_cache_w1.json
```

Send the Step 11 digest to Telegram:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/telegram_digest.py --cache adas/test_sets/video_cache_w1.json --send
```

This writes `skills/youtube-curator/delivery_log.json` with per-video message metadata for later feedback mapping.

Capture Telegram reactions into Step 12 feedback:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python -m adas.telegram_feedback \
  --delivery-log skills/youtube-curator/delivery_log.json \
  --feedback adas/test_sets/feedback.json
```

React up or down to an individual video message in Telegram, then run the above command. Recognised reactions are written into `feedback.json` and influence future alignment scoring for that video.

Append manual feedback into Step 7:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/feedback_cli.py --date 2026-05-04 --cache adas/test_sets/video_cache_w1.json --skill-version skill_003 --pick TsXhgpZRU2w=up --pick gwsaC3WiCqs=down
```

## Security and repo hygiene

- `.env` is intentionally ignored and should never be committed.
- generated caches and feedback data in `adas/test_sets/` are ignored
- archive entries under `adas/archive/skill_*/` are versioned project history
- `.env.example` is the safe template for sharing config shape without secrets

## References

- `docs/history/` holds the original design plan (`Plan.md`) and implementation checklist. Treat them as historical context when they conflict with the current docs.
- `adas/README.md` documents the ADAS workspace in more detail.
- `ARCHITECTURE.md` explains the current module layout.
- `WORKFLOW.md` explains the runnable fetch -> evaluate -> compare -> archive -> feedback -> meta-agent -> promote -> deliver -> capture loop.
- `skills/youtube-curator/README.md` explains the production skill directory.
- `cron/README.md` explains the scheduler.
