# ADAS workspace

This directory holds the components for the **Adaptive Design / evaluation / archive** side of EvoClaw.

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

Example:

```bash
cd adas
python youtube_fetcher.py --days 7 --max-per-query 10 --output video_cache_w1.json
```

### `config.py`

Central config for:

- search queries and fetch limits
- inference backend and model settings
- evaluation score weights
- path constants used by the planned ADAS loop
- nightly loop parameters like iteration counts and retry limits

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

Currently only contains `index.json`, which is the future registry for generated skills and their scores.

### `test_sets/`

Intended for cached video sets and feedback history.

Current contents are early local datasets and placeholders:

- `video_cache_test.json`
- `video_cache_w1.json` generated locally for Step 1 validation
- `feedback.json`

## Planned additions

The design in `Plan.md` expects this directory to grow with:

- `evaluator.py` for scoring candidate skills
- `meta_agent.py` for the overnight improvement loop
- `prompts/` for meta-agent and judge prompts
- generated archive folders such as `archive/skill_001/`

## Data flow

The intended lifecycle inside `adas/` is:

1. Fetch fresh or cached YouTube candidates.
2. Evaluate a candidate `SKILL.md` against cached sets.
3. Record score breakdowns and metadata in the archive.
4. Iterate via a meta agent to discover stronger skills.
5. Promote the best skill into `skills/youtube-curator/SKILL.md`.

## Notes

- Runtime-generated data in `test_sets/` and `archive/skill_*/` is gitignored.
- Secret values are loaded from the repo root `.env`.
- The current repo state is still **pre-evaluator / pre-meta-agent**.
- Transcript fetching is **best-effort**: some videos now resolve transcripts, but YouTube may still block others depending on IP/network conditions.
- The current cache shape is strong enough to begin the evaluator, because it includes `views_per_hour`, `subscriber_count`, and descriptions even when transcripts are missing.
