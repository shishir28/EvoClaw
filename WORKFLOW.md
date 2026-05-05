# EvoClaw workflow

This file explains **what actually happens today** in the codebase, and **what the future full loop is supposed to look like**.

## 1. Current runnable workflow

Today, EvoClaw supports a complete **fetch -> evaluate -> compare -> archive -> feedback** workflow.

### Step 1: Fetch candidate videos

`adas/youtube_fetcher.py`:

1. searches YouTube for configured queries
2. deduplicates video IDs
3. enriches each video with metadata
4. adds `views_per_hour`
5. adds `subscriber_count`
6. tries to attach transcripts on a best-effort basis
7. saves the result into `adas/test_sets/*.json`

Typical output today:

- `adas/test_sets/video_cache_w1.json`

### Step 2: Load an evaluation request

`adas/evaluation/loader.py`:

1. reads a candidate `SKILL.md`
2. parses its YAML frontmatter
3. loads cached videos from JSON
4. loads optional feedback history from `feedback.json`
5. assembles an `EvaluationRequest`

### Step 3: Select videos for the skill

`adas/evaluation/executor.py`:

1. reads the skill strategy from the parsed skill metadata
2. chooses the matching Python strategy executor
3. applies that strategy over the cached video records
4. returns selected video IDs plus execution notes

Supported strategies today:

- `recency`
- `engagement-velocity`
- `llm-substance-judge`

### Step 4: Score the selection

`adas/evaluation/service.py` coordinates two scoring paths.

When run from the CLI without explicit `--selected-ids`, it still executes the baseline adapter path and returns a real scored result instead of an empty template payload.

#### 4a. Algorithmic scoring

`adas/evaluation/scorer.py` scores:

- `freshness`
- `diversity`
- `alignment`

`alignment` now uses exact historical matches first, then a lightweight snapshot-similarity heuristic. It still falls back to neutral when there is no feedback history.

#### 4b. Optional LLM judging

If LLM judging is enabled, `adas/evaluation/judge.py` scores:

- `relevance`
- `substance`
- `reasoning`

It builds a prompt from `adas/prompts/eval_judge.md` and calls the configured OpenAI-compatible endpoint.

The default judge client is created lazily, so algorithmic-only runs do not pay setup cost for the LLM path.

### Step 5: Aggregate the result

`adas/evaluation/service.py`:

1. applies all dimension scores to the result
2. checks whether any dimensions are still missing
3. returns `partially_scored` if only algorithmic dimensions are present
4. returns `scored` with `total_score` once all dimensions are available

### Step 6: Compare all baseline skills on one cache

`adas/baseline/comparison.py`:

1. asks `BaselineCatalog` for the ordered baseline skill files
2. asks `BaselineEvaluationRunner` to evaluate each one against the same cache
3. asks `EvaluationResultStore` to persist one result file per skill
4. writes a `summary.json` ranking file under `adas/baseline_results/`

The required cache path is validated up front here; optional feedback still falls back to an empty history when absent.

Current saved baseline comparison on `video_cache_w1.json`:

1. `recency-first` — `7.3924`
2. `engagement-velocity` — `7.1419`
3. `llm-substance-judge` — `5.7784`

### Step 7: Archive evaluated skills

`adas/archive_runtime/service.py` and `adas/archive_runtime/store.py`:

1. read the evaluated baseline records
2. allocate or reuse `skill_###` archive IDs for the evaluation context
3. write `SKILL.md`, `result.json`, and `meta.json` under `adas/archive/skill_###/`
4. update `adas/archive/index.json` with the archive entries and best-skill metadata

Current archive snapshot:

1. `skill_003` (`recency-first`) — `7.3924`
2. `skill_002` (`engagement-velocity`) — `7.1419`
3. `skill_001` (`llm-substance-judge`) — `5.7784`

### Step 8: Append feedback history

`adas/feedback/service.py` and `adas/feedback/store.py`:

1. resolve manual feedback picks against a cache file
2. store `skill_version` plus a reusable snapshot of each reacted video
3. append the entry into `adas/test_sets/feedback.json`
4. let later evaluator runs use that history for `alignment`

### Step 9: Meta-agent generate → reflect → evaluate → archive cycle

`adas/meta_agent.py` is the CLI entrypoint; `adas/meta/loop.py` orchestrates each cycle.

One cycle does:

1. Build a `MetaContext` from archive state and feedback history (`adas/meta/context.py`)
2. Ask the LLM to generate a candidate skill JSON (`adas/meta/generator.py`)
3. Run up to `--reflect-passes` reflection rounds; each round may repair the candidate (`adas/meta/reflector.py`)
4. Validate the accepted candidate's frontmatter and name consistency locally (`adas/meta/parser.py`)
5. Check the candidate body hash against every archived SKILL.md to skip duplicates (`adas/meta/dedupe.py`)
6. Write the candidate to a temporary SKILL.md and evaluate it with the standard evaluator
7. Archive the evaluated result and return a `CycleResult` with outcome, score, and skill ID

Supported outcomes: `success`, `dedupe`, `parse_failure`, `reflect_exhausted`, `eval_error`.

## 2. Current workflow as a diagram

```text
SKILL.md + cache JSON + feedback JSON
                |
                v
      evaluation/loader.py
                |
                v
        EvaluationRequest
                |
                v
       evaluation/executor.py
                |
                v
      selected_video_ids + notes
                |
                v
      evaluation/scorer.py ----> evaluation/judge.py (optional)
                \                  /
                 \                /
                  v              v
                 evaluation/service.py
                        |
                        v
                  EvaluationResult
                        |
                        v
            baseline/comparison.py
                        |
                        v
       baseline_results/<cache-stem>/summary.json
                        |
                        v
         archive_runtime/service.py
                        |
                        v
             archive/index.json + skill_###/
                        |
                        v
            feedback/store.py + feedback.json
                        |
                        v
        meta/context.py (archive + feedback → MetaContext)
                        |
                        v
              meta/generator.py (LLM → candidate JSON)
                        |
                        v
            meta/reflector.py (LLM → verdict + repair)
                        |
                        v
       meta/parser.py (local validation + dedupe check)
                        |
                        v
         evaluation/service.py (score candidate skill)
                        |
                        v
         archive_runtime/service.py (archive result)
                        |
                        v
                CycleResult (outcome + skill_id + score)
```

## 3. What is not in the workflow yet

The following steps are still planned, not implemented:

1. deploy the winning skill automatically
2. run the production skill on a schedule
3. send the digest to Telegram
4. replace manual feedback append with Telegram reaction capture

## 4. Planned future full workflow

The intended long-term workflow is:

1. fetch fresh YouTube candidates
2. evaluate baseline and generated skills against cached sets
3. archive every result
4. let a meta-agent generate improved skills
5. reflect/debug until the candidate is valid
6. evaluate the candidate
7. update the archive and best-skill metadata
8. promote the best `SKILL.md` into `skills/youtube-curator/SKILL.md`
9. run the production skill on schedule
10. send a Telegram digest
11. collect feedback
12. feed that feedback back into future evaluations

## 5. Best commands to understand the current system

Fetch a dataset:

```bash
cd adas
python3 youtube_fetcher.py --days 7 --max-per-query 10 --output video_cache_w1.json
```

Inspect evaluator behavior on a baseline skill:

```bash
cd adas
python3 evaluator.py --skill baselines/baseline_popular.md --cache video_cache_w1.json
```

Enable LLM judging when a local compatible endpoint is available:

```bash
cd adas
python3 evaluator.py --skill baselines/baseline_curated.md --cache video_cache_w1.json --with-llm-judge
```

Run baseline comparison plus archive:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/baseline_comparison.py --cache adas/test_sets/video_cache_w1.json --archive
```

Append a manual feedback entry:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/feedback_cli.py --date 2026-05-04 --cache adas/test_sets/video_cache_w1.json --skill-version skill_003 --pick TsXhgpZRU2w=up
```

Run the Step 9 meta-agent loop:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/meta_agent.py --cache adas/test_sets/video_cache_w1.json --reflect-passes 2
```

## 6. Immediate next workflow milestone

The next useful workflow to add is:

1. promote the best archived skill into production
2. later replace manual feedback append with Telegram reaction capture
3. then wire the full scheduled runtime

That is the next missing step before EvoClaw becomes a true end-to-end daily system.
