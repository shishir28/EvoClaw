# EvoClaw architecture

This file explains the **current codebase shape** in plain language so you can understand where each concern lives without reading every module first.

## 1. Current architecture in one sentence

EvoClaw currently has a working **fetch -> evaluate -> compare -> archive -> feedback -> evolve -> promote -> deliver -> capture reactions** foundation, with scheduled runtime automation still to be built.

## 2. Main layers

| Layer | Purpose | Current files |
| --- | --- | --- |
| Data collection | Fetch YouTube candidates and cache them locally | `adas/youtube_fetcher.py` |
| Shared configuration | Centralize env-driven settings, paths, weights, and limits | `adas/config.py` |
| Evaluation internals | Coordinate request loading, skill execution, scoring, and aggregation | `adas/evaluation/` |
| Baseline comparison internals | Discover, evaluate, and persist baseline comparison runs | `adas/baseline/` |
| Archive internals | Save versioned archive entries and best-skill metadata | `adas/archive_runtime/` |
| Feedback internals | Persist feedback history and append manual feedback entries | `adas/feedback/` |
| Deployment internals | Promote the archive winner into the production skill path | `adas/deployment/` |
| Telegram delivery internals | Format, send, log the production digest, poll for reactions, and write feedback | `adas/telegram/`, `adas/telegram_digest.py`, `adas/telegram_feedback.py` |
| CLI compatibility layer | Preserve the remaining manual entrypoints while internals live in grouped packages | `adas/evaluator.py`, `adas/baseline_comparison.py`, `adas/feedback_cli.py` |
| Prompt assets | Hold reusable evaluator and meta-agent prompt templates | `adas/prompts/eval_judge.md`, `adas/prompts/meta_system.md`, `adas/prompts/meta_design.md`, `adas/prompts/meta_reflect.md` |
| Production skill target | Live deployment target for the best skill | `skills/youtube-curator/SKILL.md` |
| Scheduler stub | Planned automation entrypoints | `cron/jobs.json` |

## 3. How the modules relate

```text
youtube_fetcher.py
    -> produces cached video datasets in adas/test_sets/

evaluation/
    models.py
    loader.py
    executor.py
    scorer.py
    judge.py
    service.py

baseline/
    models.py
    catalog.py
    runner.py
    result_store.py
    comparison.py

archive_runtime/
    models.py
    store.py
    service.py

deployment/
    promoter.py

feedback/
    store.py
    service.py

telegram/
    formatter.py
    sender.py
    delivery_log.py
    service.py
    reaction_poller.py
    feedback_capture.py

top-level CLI entrypoints
    -> preserve the remaining manual command surfaces
```

## 4. Core design choices already visible in the code

### DTOs are separated from orchestration

If you come from a .NET background, `adas/evaluation/models.py` is the closest thing to a DTO/contracts file.

### File loading is separate from business logic

`adas/evaluation/loader.py` owns markdown parsing and JSON loading, so `Evaluator` does not need to understand low-level file formats.

`adas/baseline/comparison.py` now also validates its required cache input before handing off to the loader, which keeps comparison failures closer to the actual caller.

The Step 6 archive flow is also kept separate: `baseline_comparison.py` can call into `archive_service.py`, but Step 5 result persistence and Step 6 archive persistence remain different modules with different output roots.

Step 10 production promotion is also isolated in `adas/deployment/promoter.py`. The promoter reads archive state through a narrow protocol, writes deployment metadata through a small store, and copies the winning skill only when its score beats the current production record.

### Scoring is split by responsibility

- `adas/evaluation/scorer.py` handles deterministic rules
- `adas/evaluation/judge.py` handles semantic judging
- `adas/evaluation/service.py` coordinates the flow

### Feedback ingestion is validated at the boundary

`adas/feedback/service.py` validates reactions against a `VALID_REACTIONS` set before writing to disk. Unknown reaction strings (e.g. `"thumbs up"` with a space) raise `ValueError` at input time rather than silently scoring as neutral inside the scorer.

`adas/feedback/store.py` writes feedback via an atomic temp-file rename so a crash mid-write cannot corrupt `feedback.json`.

### Alignment scoring uses explicit named constants

`adas/evaluation/scorer.py` defines `_MIN_ALIGNMENT_SIMILARITY`, `_CHANNEL_WEIGHT`, `_TOPIC_WEIGHT`, and `_DURATION_WEIGHT` as named module-level constants so the heuristic thresholds are visible and tunable without hunting through arithmetic expressions.

### Skill execution is replaceable

`adas/evaluation/executor.py` is intentionally a Python adapter for now. It gives you a working execution path today while keeping the door open for a future real OpenClaw runtime.

### Expensive judge setup is lazy

`adas/evaluation/service.py` keeps the default `LLMJudge` lazy, so baseline-only and algorithmic-only runs do not eagerly create model client state.

### Fetching is internally decomposed

Inside `adas/youtube_fetcher.py`, the fetcher is split into:

- `YouTubeAPIClient`
- `TranscriptProvider`
- `VideoCacheRepository`
- `YouTubeFetcher`

That keeps API access, transcript attachment, cache persistence, and orchestration separate enough to follow.

## 5. Important data objects

| Type | Meaning |
| --- | --- |
| `SkillDocument` | Parsed `SKILL.md` plus YAML frontmatter metadata |
| `VideoRecord` | Normalized cached YouTube video record |
| `FeedbackVideoSnapshot` | Stored video snapshot used for later alignment scoring |
| `FeedbackEntry` | One feedback history record from `feedback.json` |
| `EvaluationRequest` | Combined input for an evaluation run |
| `DimensionScore` | One weighted score entry in the result |
| `EvaluationResult` | Final evaluation output, partial or complete |
| `ArchiveIndexEntry` | One archived skill summary in `adas/archive/index.json` |
| `ArchiveIndex` | Archive-wide best-skill metadata plus archived entries |

## 6. What is implemented vs planned

### Implemented now

- real YouTube fetching and cache generation
- typed settings and path/config organization
- evaluator request loading
- baseline strategy execution through a Python adapter
- algorithmic scoring
- optional LLM judging
- weighted aggregation
- baseline comparison persistence and ranking on `video_cache_w1.json`
- archive entry creation under `adas/archive/skill_*`
- best-skill tracking in `adas/archive/index.json`
- feedback persistence plus snapshot-based alignment scoring
- first-pass meta-agent orchestration for generate -> reflect -> evaluate -> archive
- opt-in production skill promotion with `deployment.json` metadata
- Telegram digest delivery with `delivery_log.json` metadata — live send confirmed
- Telegram reaction capture via polling, mapping 👍/👎 reactions to feedback entries through the Step 7 service

### Planned later

- cron-driven end-to-end automation

## 7. Best files to read first

If you want the easiest learning path through the code:

1. `README.md`
2. `WORKFLOW.md`
3. `adas/README.md`
4. `adas/evaluation/models.py`
5. `adas/evaluation/loader.py`
6. `adas/evaluation/service.py`
7. `adas/evaluation/executor.py`
8. `adas/evaluation/scorer.py`
9. `adas/evaluation/judge.py`
10. `adas/baseline/comparison.py`
11. `adas/archive_runtime/service.py`
12. `adas/archive_runtime/store.py`
13. `adas/deployment/promoter.py`
14. `adas/feedback/service.py`
15. `adas/feedback/store.py`
16. `adas/youtube_fetcher.py`

## 8. How to run unit tests

The current suite is **270 passing tests**.

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run all tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/adas/test_algorithmic_scorer.py -v

# Run a single test class
python3 -m pytest tests/adas/test_skill_executor.py::TestLooksEnglish -v

# Run a single test
python3 -m pytest tests/adas/test_evaluator.py::TestAggregateWeightedScore::test_all_tens_gives_10 -v

# Stop on first failure
python3 -m pytest tests/ -v -x

# Show just a summary (no per-test output)
python3 -m pytest tests/
```
