# ADAS workspace

This directory holds the **fetch, evaluate, and future archive** side of EvoClaw.

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

The evaluator now defines:

- orchestration of the evaluator flow
- a `score()` orchestration path for explicit selected video IDs or adapter-selected picks
- composition of the smaller evaluator components listed below
- constructor injection points for the main evaluator collaborators
- smaller private helper methods so the main score path reads top-down

### `evaluator_loader.py`

Owns request loading concerns that used to sit inside the data contracts:

- skill markdown loading and frontmatter parsing
- cache loading
- feedback history loading
- assembly of `EvaluationRequest`

### `evaluator_models.py`

Owns the evaluator DTO-style dataclasses:

- skill documents
- cached video records
- feedback entries
- evaluation request/result types
- dimension score records

### `algorithmic_scorer.py`

Owns the non-LLM evaluator dimensions:

- freshness
- diversity
- alignment placeholder

It now uses explicit evaluator model types instead of loose `Any`-style contracts.

### `llm_judge.py`

Owns prompt-based judging for:

- relevance
- substance
- reasoning

It now separates:

- prompt template loading
- chat completion transport
- score parsing and judge orchestration

### `skill_executor.py`

Owns Python-adapter execution for the current baseline strategies.

It now uses separate strategy executors behind a registry instead of one central conditional dispatcher.

### `baseline_catalog.py`

Owns the ordered list of Step 5 baseline skill files.

This keeps baseline discovery separate from comparison orchestration, so the comparison flow does not need to know where the baseline files live.

### `baseline_evaluation_models.py`

Owns the Step 5 result DTOs:

- `BaselineEvaluationRecord`

This keeps comparison output shape explicit and reusable across the runner and the persistence layer.

### `baseline_evaluation_runner.py`

Owns multi-skill evaluation orchestration for Step 5.

It loops through a list of baseline skill paths, calls `Evaluator.score(...)`, and records either a scored result or a failure without taking on any file-writing responsibility.

### `evaluation_result_store.py`

Owns Step 5 persistence only:

- writes one JSON file per baseline result
- writes a `summary.json` ranking file

It is intentionally separate from the future Step 6 archive layer.

### `baseline_comparison.py`

Owns the end-to-end Step 5 comparison flow by composing:

1. `BaselineCatalog`
2. `BaselineEvaluationRunner`
3. `EvaluationResultStore`

It also exposes a small CLI for running the three baselines on one cache and saving the outputs.

### Evaluator runtime path

The evaluator runtime is now split cleanly:

1. `Evaluator` loads request data and orchestrates the flow
2. `evaluator_loader.py` assembles the request from files
3. `evaluator_models.py` provides the request/result data structures
4. `skill_executor.py` selects videos for supported baseline skills
5. `algorithmic_scorer.py` scores the rule-based dimensions
6. `llm_judge.py` scores the semantic dimensions
7. `Evaluator` aggregates the final result
8. `baseline_comparison.py` can run all baseline skills against one cache and persist the results

Current limitation: real OpenClaw execution and the later meta-agent loop are not implemented yet.

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

Right now this contains only `index.json`, and it is still empty:

- `best_skill_id` is `null`
- `best_score` is `0.0`
- `skills` is an empty list

Archive entry generation is the next later phase; no `archive/skill_*` folders exist yet.

### `baseline_results/`

Holds Step 5 comparison outputs that are intentionally separate from the future archive layer.

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
- `feedback.json` with an empty `history` list

## Planned additions

The design in `Plan.md` expects this directory to grow with:

- `meta_agent.py` for the overnight improvement loop
- additional prompts for the meta-agent loop
- generated archive folders such as `archive/skill_001/`

## Data flow

The current lifecycle inside `adas/` is:

1. Fetch fresh or cached YouTube candidates.
2. Load a candidate `SKILL.md`, cache JSON, and optional feedback history.
3. Execute supported baseline strategies through the Python adapter, or score explicit selected IDs.
4. Score algorithmic dimensions first, then optionally apply LLM-judged dimensions.
5. Aggregate the final weighted result.
6. Optionally run all baselines against one cache and persist a comparison summary.

The planned later lifecycle adds:

6. Record score breakdowns and metadata in the archive.
7. Iterate via a meta agent to discover stronger skills.
8. Promote the best skill into `skills/youtube-curator/SKILL.md`.

## Notes

- Runtime-generated data in `test_sets/` and `archive/skill_*/` is gitignored.
- Secret values are loaded from the repo root `.env`.
- The current repo state is **post-evaluator / pre-archive / pre-meta-agent**.
- Step 5 is now complete for the current `video_cache_w1.json` dataset.
- Transcript fetching is **best-effort**: some videos now resolve transcripts, but YouTube may still block others depending on IP/network conditions.
- The current cache shape is strong enough to begin the evaluator, because it includes `views_per_hour`, `subscriber_count`, and descriptions even when transcripts are missing.
- The next concrete implementation step is to define the archive layer and promote Step 5 outputs into Step 6 persistence.
- See the repo-level `ARCHITECTURE.md` and `WORKFLOW.md` files for the simplest high-level explanation.
