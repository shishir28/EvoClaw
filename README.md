# EvoClaw

EvoClaw is an **ADAS-style, self-improving YouTube curator** for AI and entrepreneurship content. The target system runs inside a NemoClaw/OpenClaw environment, fetches candidate videos, evaluates curation strategies, evolves better `SKILL.md` prompts over time, and can now run a manual top-3 Telegram digest while full scheduling remains a later step.

The repository is currently at the **working fetcher + evaluator + baseline comparison + archive + feedback + meta-agent + skill promotion + Telegram delivery + Telegram reaction capture stage**:

- a YouTube fetcher with caching, `subscriber_count` enrichment, and best-effort transcript support
- a modular evaluator stack with DTO models, request loading, algorithmic scoring, optional LLM judging, and weighted aggregation
- a Python adapter that executes the current baseline `SKILL.md` strategies over cached videos
- a Step 5 comparison flow that evaluates all baselines against one cache and persists detailed results
- a Step 6 archive flow that writes `SKILL.md`, `result.json`, `meta.json`, and best-skill metadata under `adas/archive/`
- a Step 7 feedback flow that validates reactions, persists video snapshots atomically, and turns `alignment` into a real heuristic preference signal using channel, topic, and duration similarity
- a Step 9 meta-agent flow that builds prompt context, generates a candidate skill, runs reflection passes, validates the candidate locally, evaluates it, and archives successful runs
- a Step 10 skill promoter that copies the archive winner into `skills/youtube-curator/SKILL.md` only when it beats the recorded production deployment
- a Step 11 Telegram delivery flow that runs the promoted production skill against a cache, formats the top 3 picks, sends them through the Bot API, and records delivery metadata in `delivery_log.json` — live send confirmed working
- a Step 12 Telegram reaction capture flow that polls for 👍/👎 reactions on digest messages, maps them back to the delivered video picks via `delivery_log.json`, and writes `FeedbackEntry` records to `feedback.json` through the existing Step 7 feedback service
- lazy default LLM-judge initialization so evaluator construction does not require model client setup unless semantic judging is enabled
- evaluator and comparison CLIs with safer defaults: evaluator runs a real scoring flow by default, and baseline comparison fails fast when the required cache file is missing
- typed shared configuration for search, inference, paths, and scoring weights
- three hand-written baseline skills plus a production `SKILL.md` target
- a cron configuration stub for future automation
- a focused pytest suite covering the evaluator path plus Step 5 through Step 11 orchestration

## Target architecture

The planned end-to-end loop is:

1. Fetch candidate videos from YouTube.
2. Score candidate curation skills on cached datasets.
3. Use a meta agent to propose improved `SKILL.md` strategies.
4. Archive results and deploy the best-performing skill.
5. Run the production skill on a schedule.
6. Send picks to Telegram and feed the resulting feedback back into evaluation.

## Repository layout

```text
EvoClaw/
├── adas/
│   ├── archive/                  # Versioned archive entries and best-skill index
│   ├── archive_runtime/          # Step 6 archive models, store, and service
│   ├── baseline/                 # Step 5 baseline comparison internals
│   ├── baseline_results/         # Saved Step 5 comparison outputs
│   ├── baselines/                # Seed curation strategies
│   ├── config.py                 # Shared configuration
│   ├── deployment/               # Step 10 production skill promotion
│   ├── evaluation/               # Evaluator models, loader, scorer, judge, executor, service
│   ├── feedback/                 # Step 7 feedback store and append service
│   ├── meta/                     # Step 9 meta-agent context, generation, reflection, parsing
│   ├── telegram/                 # Step 11-12 Telegram digest, sender, reaction poller, feedback capture
│   ├── baseline_comparison.py    # CLI entrypoint and compatibility wrapper
│   ├── evaluator.py              # CLI entrypoint and compatibility wrapper
│   ├── feedback_cli.py           # Manual feedback append CLI
│   ├── meta_agent.py             # Step 9 meta-agent CLI entrypoint
│   ├── telegram_digest.py        # Step 11 Telegram digest CLI
│   ├── telegram_feedback.py      # Step 12 Telegram reaction feedback capture CLI
│   ├── prompts/                  # Evaluator prompts
│   ├── test_sets/                # Local caches and feedback artifacts
│   └── youtube_fetcher.py        # YouTube data collection and caching
├── cron/
│   ├── README.md
│   └── jobs.json                 # Planned automation schedule
├── skills/
│   └── youtube-curator/
│       ├── README.md
│       └── SKILL.md              # Current production skill target
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
- `adas/evaluation/` for evaluator internals grouped by domain
- `adas/baseline/` for baseline comparison internals grouped by domain
- `adas/archive_runtime/` for Step 6 archive internals grouped by domain
- `adas/feedback/` for Step 7 feedback persistence and append logic
- `adas/meta/` for Step 9 meta-agent orchestration internals
- `adas/deployment/` for Step 10 production skill promotion
- `adas/telegram/` for Step 11-12 digest formatting, sending, delivery metadata logging, reaction polling, and feedback capture
- top-level `adas/evaluator.py`, `adas/baseline_comparison.py`, `adas/feedback_cli.py`, `adas/meta_agent.py`, `adas/telegram_digest.py`, and `adas/telegram_feedback.py` as CLI entrypoints
- `adas/prompts/eval_judge.md`
- `adas/prompts/meta_system.md`, `adas/prompts/meta_design.md`, and `adas/prompts/meta_reflect.md`
- `adas/baselines/*.md`
- `adas/baseline_results/video_cache_w1/summary.json`
- `adas/archive/index.json`
- `skills/youtube-curator/SKILL.md`
- `skills/youtube-curator/delivery_log.json` after the first Step 11 run
- `cron/jobs.json`
- local Step 1 validation: real fetch works and produces a reusable cache in `adas/test_sets/video_cache_w1.json`
- evaluator architecture cleanup: smaller modules, DTO separation, injected collaborators, and readability-focused helpers
- baseline comparison results saved under `adas/baseline_results/video_cache_w1/`
- pytest coverage for evaluator, loader, scorer, executor, and Step 5 comparison modules, including evaluator CLI helpers
- pytest coverage for `SkillPromoter`, deployment metadata, and opt-in meta-agent promotion wiring

Current baseline comparison snapshot on `video_cache_w1.json`:

- `recency-first`: **7.3924**
- `engagement-velocity`: **7.1419**
- `llm-substance-judge`: **5.7784**

Current archive snapshot:

- `skill_003` (`recency-first`) is the current best archived skill at **7.3924**
- `skill_001` to `skill_003` store the three baseline seeds with `SKILL.md`, `result.json`, and `meta.json`
- `adas/archive/index.json` now tracks archive context and best-skill metadata

Current feedback snapshot:

- `adas/test_sets/feedback.json` now uses a stable `{ "history": [...] }` wrapper
- feedback entries can persist `skill_version` plus a per-pick video snapshot for later alignment scoring
- alignment now uses exact history matches first, then snapshot similarity over channel/topic/duration signals

Current deployment snapshot:

- `adas/deployment/promoter.py` can promote the archive winner into `skills/youtube-curator/SKILL.md`
- promotion writes `deployment.json` beside the production skill and skips when the recorded deployment score is equal or better

Current delivery snapshot:

- `adas/telegram/service.py` runs the production skill against a cache and builds a Telegram digest
- `adas/telegram/sender.py` sends the digest through Telegram's `sendMessage` API when explicitly enabled
- `adas/telegram_digest.py` defaults to dry-run mode so message formatting can be checked safely
- `skills/youtube-curator/delivery_log.json` records delivery time, selected video IDs, digest text, and Telegram message ID when available
- live send confirmed working with real credentials (`telegram_message_id: 2`)

Current reaction capture snapshot:

- `adas/telegram/reaction_poller.py` polls `getUpdates` for `message_reaction` events
- `adas/telegram/feedback_capture.py` maps reactions to delivery records and writes `FeedbackEntry` objects via the Step 7 service
- `adas/telegram_feedback.py` is the CLI (`--delivery-log`, `--feedback`, `--offset-file`)
- offset state is persisted in `reaction_poll_offset.json` next to the delivery log

Current next milestone:

- wire cron automation for the full scheduled runtime (Step 13)

Planned but not yet implemented:

- real OpenClaw execution
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

### Docker scheduler

EvoClaw can run its scheduled jobs inside Docker instead of installing cron on
the host:

```bash
docker compose up -d --build evoclaw
docker compose logs -f evoclaw
```

The compose service bind-mounts this repository at `/app`. Any files created by
scheduled runs are written back into the current directory structure, including
`cron/logs/`, `adas/archive/`, `adas/test_sets/feedback.json`, and
`skills/youtube-curator/` delivery/deployment files.

When using a vLLM server published on the host at port `9000`, the container uses
`http://host.docker.internal:9000/v1` by default. Override it with
`EVOCLAW_LLM_BASE_URL` if needed.

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

This writes `skills/youtube-curator/delivery_log.json` with the digest metadata for later feedback mapping.

Capture Telegram reactions into Step 12 feedback:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python -m adas.telegram_feedback \
  --delivery-log skills/youtube-curator/delivery_log.json \
  --feedback adas/test_sets/feedback.json
```

React 👍 or 👎 to the digest message in Telegram, then run the above command. Recognised reactions are written into `feedback.json` and influence future alignment scoring.

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

- `Plan.md` describes the full intended design, phases, and success metrics.
- `adas/README.md` documents the ADAS workspace in more detail.
- `ARCHITECTURE.md` explains the current module layout, including the Step 6 to Step 10 modules.
- `WORKFLOW.md` explains the runnable fetch -> evaluate -> compare -> archive -> feedback -> meta-agent -> promote flow.
- `skills/youtube-curator/README.md` explains the production skill directory.
- `cron/README.md` explains the planned scheduler wiring.
