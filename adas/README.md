# ADAS workspace

This directory holds the **fetch, evaluate, compare, archive, feedback, evolve, and promote** side of EvoClaw.

The package layout was recently reorganized to group internals by domain:

- `evaluation/` holds evaluator internals
- `baseline/` holds baseline comparison internals
- `archive_runtime/` holds archive internals
- `feedback/` holds Step 7 feedback persistence and append logic
- `deployment/` holds Step 10 production skill promotion
- top-level CLI files remain for manual runs; most internal imports now target the grouped packages directly

## What is here now

### `youtube_fetcher.py`

The fetcher already supports:

- YouTube Data API search across multiple queries
- metadata enrichment for returned videos
- derived `views_per_hour`
- channel `subscriber_count` enrichment via the YouTube channels endpoint
- optional transcript retrieval through `youtube-transcript-api`
- cache save/load helpers
- a CLI entrypoint for manual refreshes

Internally it is now split into smaller collaborators:

- `YouTubeAPIClient` for search and enrichment calls
- `TranscriptProvider` for best-effort transcript attachment
- `VideoCacheRepository` for cache persistence
- typed payload contracts so the fetcher flow is easier to follow than anonymous `dict` shapes

Example:

```bash
cd adas
python3 youtube_fetcher.py --days 7 --max-per-query 10 --output video_cache_w1.json
```

### `config.py`

Central config for:

- search queries and fetch limits
- inference backend and model settings
- evaluation score weights
- path constants used by the planned ADAS loop
- nightly loop parameters like iteration counts and retry limits

It now also exposes a typed `SETTINGS` object as the source of truth, while keeping the older constant-style imports working for existing modules.

For readability, `load_settings()` is now composed from smaller section builder helpers instead of one large configuration block.

### `evaluator.py`

`evaluator.py` is now the thin CLI/compatibility layer.

The real evaluator implementation lives under `evaluation/service.py`, and still defines:

- orchestration of the evaluator flow
- a `score()` orchestration path for explicit selected video IDs or adapter-selected picks
- composition of the smaller evaluator components listed below
- constructor injection points for the main evaluator collaborators
- smaller private helper methods so the main score path reads top-down
- lazy default `LLMJudge` creation so model client setup only happens when semantic judging is enabled
- a CLI helper path that always returns a real scored result instead of an empty template shell

### `evaluation/loader.py`

Owns request loading concerns that used to sit inside the data contracts:

- skill markdown loading and frontmatter parsing
- cache loading
- feedback history loading
- assembly of `EvaluationRequest`

### `evaluation/models.py`

Owns the evaluator DTO-style dataclasses:

- skill documents
- cached video records — with `transcript_or_description`, `has_transcript`, and `content_source` convenience properties
- feedback entries
- evaluation request/result types
- dimension score records

### `evaluation/scorer.py`

Owns the non-LLM evaluator dimensions:

- freshness — base 6.0 for ≤168 h, linear decay to 0 at 720 h, +4.0 bonus for ≤48 h; future-dated `published_at` scores 0.0
- diversity — channel uniqueness ratio + Jaccard topical similarity, averaged
- alignment — exact historical matches first, then heuristic similarity over channel, topic, and duration using persisted feedback snapshots

Alignment thresholds are declared as named module-level constants (`_MIN_ALIGNMENT_SIMILARITY`, `_CHANNEL_WEIGHT`, `_TOPIC_WEIGHT`, `_DURATION_WEIGHT`) so they are tunable without hunting through arithmetic expressions.

It now uses explicit evaluator model types instead of loose `Any`-style contracts.

### `feedback/store.py`

Owns Step 7 feedback persistence:

- loads `adas/test_sets/feedback.json`
- saves the stable `{ "history": [...] }` wrapper via an atomic temp-file rename so a crash mid-write cannot corrupt the file
- keeps one source of truth for feedback history reads/writes

### `feedback/service.py`

Owns Step 7 manual feedback ingestion:

1. validates reactions at input time against `VALID_REACTIONS` frozenset — unknown strings (e.g. `"thumbs up"` with a space) raise `ValueError` immediately rather than silently scoring as neutral
2. validates empty date, empty picks list, empty video ID, unknown video IDs, and duplicate video IDs
3. resolves video IDs against an available cache dataset
4. stores a `FeedbackVideoSnapshot` of the reacted video for future alignment scoring
5. appends the new entry through `FeedbackStore`

### `feedback_cli.py`

Manual CLI entrypoint for Step 7. It appends feedback entries using a cache file so stored picks include a reusable video snapshot.

### `evaluation/judge.py`

Owns prompt-based judging for:

- relevance
- substance
- reasoning

It now separates:

- prompt template loading
- chat completion transport — created lazily only when `judge_dimensions()` is first called
- score parsing and judge orchestration
- `_extract_json_object()` tries a full-response `json.loads` first, then falls back to a JSON scanner for preamble-wrapped responses

### `evaluation/executor.py`

Owns Python-adapter execution for the current baseline strategies.

It now uses separate strategy executors behind a registry instead of one central conditional dispatcher.

### `baseline/catalog.py`

Owns the ordered list of Step 5 baseline skill files.

This keeps baseline discovery separate from comparison orchestration, so the comparison flow does not need to know where the baseline files live.

### `baseline/models.py`

Owns the Step 5 result DTOs:

- `BaselineEvaluationRecord`

This keeps comparison output shape explicit and reusable across the runner and the persistence layer.

### `baseline/runner.py`

Owns multi-skill evaluation orchestration for Step 5.

It loops through a list of baseline skill paths, calls `Evaluator.score(...)`, and records either a scored result or a failure without taking on any file-writing responsibility.

### `baseline/result_store.py`

Owns Step 5 persistence only:

- writes one JSON file per baseline result
- writes a `summary.json` ranking file

It is intentionally separate from the Step 6 archive layer.

### `baseline_comparison.py`

`baseline_comparison.py` is now the CLI/compatibility layer over `baseline/comparison.py`, which owns the end-to-end Step 5 comparison flow by composing:

1. `BaselineCatalog`
2. `BaselineEvaluationRunner`
3. `EvaluationResultStore`

It also exposes a small CLI for running the three baselines on one cache and saving the outputs.

The comparison service now fails fast when the required cache file is missing, while still treating feedback history as optional, and it can optionally forward the evaluated records into the Step 6 archive layer with `--archive`.

### `archive_runtime/models.py`

Owns the Step 6 archive DTOs:

- `ArchiveIndex`
- `ArchiveIndexEntry`

These keep the archive index shape explicit instead of writing anonymous JSON blobs from orchestration code.

### `archive_runtime/store.py`

Owns Step 6 archive persistence:

- loads and saves `adas/archive/index.json`
- allocates or reuses `skill_###` archive IDs
- writes `SKILL.md`, `result.json`, and `meta.json` for each archive entry

### `archive_runtime/service.py`

Owns Step 6 archive orchestration:

1. reads evaluated records
2. builds archive metadata and dedupe keys
3. writes each archive entry through `ArchiveStore`
4. updates `best_skill_id` and `best_score`

### Evaluator runtime path

The evaluator runtime is now split cleanly:

1. `evaluation/service.py` loads request data and orchestrates the flow
2. `evaluation/loader.py` assembles the request from files
3. `evaluation/models.py` provides the request/result data structures
4. `evaluation/executor.py` selects videos for supported baseline skills
5. `evaluation/scorer.py` scores the rule-based dimensions
6. `evaluation/judge.py` scores the semantic dimensions
7. `Evaluator` aggregates the final result
8. `baseline/comparison.py` can run all baseline skills against one cache and persist the results
9. `archive_runtime/service.py` can persist those evaluated records into the archive
10. `feedback/service.py` can append manual feedback entries for later alignment scoring
11. `deployment/promoter.py` can promote the archive winner into production

Current limitation: the meta-agent runs a local generate→reflect→evaluate→archive loop with opt-in promotion. Manual Telegram delivery now exists, but scheduled runtime wiring and Telegram reaction capture still do not.

### `meta/`

Owns Step 9 meta-agent internals:

- `context.py` builds compact archive and feedback summaries for prompt inputs
- `generator.py` composes `meta_system.md` + `meta_design.md` and extracts candidate JSON
- `reflector.py` runs `meta_reflect.md` and returns a repaired candidate plus verdict/checks
- `parser.py` validates candidate JSON and YAML frontmatter locally before evaluation
- `dedupe.py` prevents trivial archive duplicates based on normalized skill-body hashes
- `loop.py` orchestrates generate -> reflect -> validate -> evaluate -> archive
- `loop.py` can optionally call the Step 10 promoter after successful archive writes

### `meta_agent.py`

Step 9 CLI entrypoint for the first local meta-agent loop. It supports:

- `--cache`
- `--feedback`
- `--archive-dir`
- `--design-goal`
- `--reflect-passes`
- `--cycles`
- `--deploy-best`
- `--production-skill`
- `--deployment-record`

### `deployment/promoter.py`

Owns Step 10 production skill promotion:

1. reads archive best-skill metadata
2. resolves the archived winner's `SKILL.md`
3. compares it against the current deployment metadata
4. copies the winner into `skills/youtube-curator/SKILL.md` only when the score improves
5. writes `deployment.json` beside the production skill

### `baselines/`

Three seed skill designs for bootstrapping the search space:

- `baseline_recency.md`
- `baseline_popular.md`
- `baseline_curated.md`

These represent three different curation philosophies:

1. newest first
2. fastest-growing engagement
3. LLM-judged substance

### `archive/`

This now holds the Step 6 archive state:

- `index.json` tracks archived skills, their evaluation context, and the current best skill
- `skill_001/` to `skill_003/` store the archived baseline seeds

Current best archive entry:

- `skill_003` → `recency-first` with **7.3924**

### `baseline_results/`

Holds Step 5 comparison outputs that are intentionally separate from the archive layer.

Current saved output:

- `baseline_results/video_cache_w1/summary.json`
- `baseline_results/video_cache_w1/results/baseline_recency.json`
- `baseline_results/video_cache_w1/results/baseline_popular.json`
- `baseline_results/video_cache_w1/results/baseline_curated.json`

Latest recorded ranking on `video_cache_w1.json`:

1. `recency-first` — `7.3924`
2. `engagement-velocity` — `7.1419`
3. `llm-substance-judge` — `5.7784`

### `test_sets/`

Holds cached video sets and feedback history.

Current contents are:

- `video_cache_test.json`
- `video_cache_w1.json` generated locally for Step 1 validation
- `feedback.json` with a stable `history` wrapper for stored feedback entries

## Planned additions

The design in `Plan.md` expects this directory to grow with:

- further generated archive folders as the meta-agent proposes and archives new skills
- Telegram feedback capture around the production skill

## Data flow

The current lifecycle inside `adas/` is:

1. Fetch fresh or cached YouTube candidates.
2. Load a candidate `SKILL.md`, cache JSON, and optional feedback history.
3. Execute supported baseline strategies through the Python adapter, or score explicit selected IDs.
4. Score algorithmic dimensions first, then optionally apply LLM-judged dimensions.
5. Aggregate the final weighted result.
6. Optionally run all baselines against one cache and persist a comparison summary.
7. Optionally archive those evaluated results into `adas/archive/skill_###/`.

The current lifecycle now also adds:

8. Build archive + feedback prompt context for the meta-agent.
9. Generate a candidate skill, run reflection passes, validate it, then evaluate and archive it.
10. Optionally promote the archive winner into `skills/youtube-curator/SKILL.md` with `--deploy-best`.

The planned later lifecycle still adds:

11. Run the production skill on a schedule.
12. Capture Telegram reactions and feed them back into evaluation.

## Unit tests

The test suite lives in `tests/adas/` and mirrors the source layout. Shared builder utilities live in `tests/adas/builders.py`.

**Current status:** the suite now covers Step 11 delivery in addition to the earlier evaluator, archive, meta-agent, and promotion flows.

| Test file | Covers |
|---|---|
| `test_algorithmic_scorer.py` | freshness, diversity, alignment |
| `test_skill_executor.py` | filter helpers, all three strategies, registry |
| `test_evaluator_loader.py` | frontmatter parsing, skill/cache/feedback loading |
| `test_evaluator_models.py` | `VideoRecord` properties (`has_transcript`, `content_source`) |
| `test_evaluator.py` | scoring paths, validation, aggregation |
| `test_evaluator_cli.py` | CLI helpers, lazy judge init |
| `test_llm_judge.py` | lazy chat client, prompt building, JSON extraction |
| `test_youtube_fetcher.py` | `TranscriptProvider` unavailability guard |
| `test_baseline_catalog.py` | skill path discovery and missing-file error |
| `test_baseline_evaluation_runner.py` | run loop, failure isolation |
| `test_evaluation_result_store.py` | JSON persistence, ranking order |
| `test_baseline_comparison.py` | end-to-end orchestration, archive wiring |
| `test_archive_service.py` | archive writes, ID reuse, best-skill tracking |
| `test_feedback_store.py` | feedback persistence and manual append flow |
| `test_meta_context.py` | archive/feedback summary building for prompt context |
| `test_meta_generator.py` | meta prompt composition and candidate extraction |
| `test_meta_reflector.py` | reflection verdicts, repairs, and prompt composition |
| `test_meta_parser.py` | JSON extraction and local candidate/frontmatter validation |
| `test_meta_dedupe.py` | normalized duplicate-skill detection |
| `test_meta_loop.py` | generate/reflect/evaluate/archive orchestration and opt-in promotion |
| `test_meta_agent_cli.py` | CLI forwarding for cycles, reflection passes, and deployment flags |
| `test_skill_promoter.py` | production promotion rules and deployment metadata |
| `test_telegram_formatter.py` | digest pick summaries, age/duration formatting, final message shape |
| `test_telegram_sender.py` | Telegram Bot API request/response handling |
| `test_telegram_service.py` | production selection, formatting, and delivery-log orchestration |
| `test_telegram_digest_cli.py` | CLI forwarding for dry-run vs send mode |

Builder utilities available to all tests:

- `video()` — `VideoRecordBuilder` fluent builder
- `skill()` — `SkillDocumentBuilder` fluent builder (supports `with_description()`)
- `FeedbackFactory` — `all_up()`, `all_down()`, `mixed()`
- `make_request()` — `EvaluationRequest` factory
- `make_result()` — `EvaluationResult` factory with all dimensions at `None`
- `make_scored_result(skill_name, total_score)` — pre-scored result factory

```bash
python3 -m pytest tests/ -v          # run all
python3 -m pytest tests/ -x          # stop on first failure
python3 -m pytest tests/adas/test_archive_service.py -v  # one file
```

## Notes

- Runtime-generated caches in `test_sets/` are gitignored, but archive history under `archive/skill_*/` is versioned.
- Secret values are loaded from the repo root `.env`.
- The current repo state is **post-evaluator / post-archive / first meta-agent loop / Step 10 promoter / Step 11 delivery runtime**.
- Step 5 and Step 6 are complete for the current `video_cache_w1.json` dataset.
- Transcript fetching is **best-effort**: some videos now resolve transcripts, but YouTube may still block others depending on IP/network conditions.
- The current cache shape is strong enough to begin the evaluator, because it includes `views_per_hour`, `subscriber_count`, and descriptions even when transcripts are missing.
- The next concrete implementation step is Step 12: capture Telegram reactions and map them into feedback history.
- See the repo-level `ARCHITECTURE.md` and `WORKFLOW.md` files for the simplest high-level explanation.
