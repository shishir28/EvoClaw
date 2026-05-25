# EvoClaw workflow

This file explains the runnable EvoClaw loop in the current codebase.

## 1. Current runnable workflow

Today, EvoClaw supports a complete **fetch -> evaluate -> compare -> archive -> feedback -> evolve -> promote -> deliver -> capture reactions** workflow.

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

### Step 7: Archive evaluated skills

`adas/archive_runtime/service.py` and `adas/archive_runtime/store.py`:

1. read the evaluated baseline records
2. allocate or reuse `skill_###` archive IDs for the evaluation context
3. write `SKILL.md`, `result.json`, and `meta.json` under `adas/archive/skill_###/`
4. update `adas/archive/index.json` with the archive entries and best-skill metadata

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

Supported outcomes: `success`, `dedupe`, `parse_failure`, `reflect_exhausted`, `eval_error`, `deploy_error`.

### Step 10: Promote the archive winner into production

`adas/deployment/promoter.py` owns the production promotion rule.

It:

1. reads `adas/archive/index.json`
2. resolves the current `best_skill_id`
3. compares archive `best_score` against the recorded production deployment
4. copies the winning archived `SKILL.md` into `skills/youtube-curator/SKILL.md` only when it improves production
5. writes `deployment.json` beside the production skill

The meta-agent keeps promotion opt-in through `--deploy-best`.

### Step 11: Send a Telegram digest

`adas/telegram/service.py` orchestrates the delivery path:

1. loads `skills/youtube-curator/SKILL.md` through the evaluator + executor path
2. selects the top 3 videos
3. formats them into a Telegram-friendly digest with title, channel, URL, and `why_watch` text
4. sends the digest through Telegram's `sendMessage` API when `--send` is used
5. sends one Telegram message per selected video when `--send` is used
6. appends a `DeliveryRecord` to `skills/youtube-curator/delivery_log.json` with aggregate message IDs, per-pick message IDs, and selected video IDs

### Step 12: Capture Telegram reactions as feedback

`adas/telegram/feedback_capture.py` closes the human-feedback loop:

1. loads `delivery_log.json` to build a `message_id → DeliveryRecord` map
2. polls Telegram's `getUpdates` for `message_reaction` events via `adas/telegram/reaction_poller.py`
3. matches each reaction's `message_id` to a known delivery record
4. maps recognised emoji (👍/👎 and common aliases) to `VALID_REACTIONS`
5. loads the original `VideoRecord` data from the delivery record's `cache_path`
6. writes one `FeedbackEntry` per matched reaction through `FeedbackService`, targeting the reacted video when per-pick message metadata is available
7. persists the last processed `update_id` to `reaction_poll_offset.json` to avoid reprocessing on subsequent runs

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
          deployment/promoter.py (--deploy-best)
                        |
                        v
                CycleResult (outcome + skill_id + score + promotion)
                        |
                        v
          telegram/service.py (--send → delivery_log.json)
                        |
                        v
        telegram/reaction_poller.py (getUpdates → ReactionUpdate)
                        |
                        v
        telegram/feedback_capture.py (→ feedback.json via FeedbackService)
```

## 3. Scheduled runtime

`cron/jobs.json` is the canonical schedule source, and NemoClaw/OpenShell owns when those jobs fire:

1. `refresh-video-cache` refreshes the YouTube cache at 00:30.
2. `adas-evolution` runs meta-agent cycles at 01:30 and promotes a better archive winner when available.
3. `morning-digest` sends the production picks at 04:30.
4. `reaction-capture` polls Telegram reactions at 08:30 and writes feedback.

## 4. End-to-end workflow shape

1. fetch fresh YouTube candidates
2. evaluate baseline and generated skills against cached sets
3. archive every result
4. let a meta-agent generate improved skills
5. reflect/debug until the candidate is valid
6. evaluate the candidate
7. update the archive and best-skill metadata
8. promote the best `SKILL.md` into `skills/youtube-curator/SKILL.md`
9. run the production skill on schedule
10. send Telegram messages for the selected videos
11. collect per-video feedback
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

Run the meta-agent loop and promote the best archived skill if it beats production:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python adas/meta_agent.py --cache adas/test_sets/video_cache_w1.json --reflect-passes 2 --deploy-best
```

Run the Step 11 digest flow in dry-run mode:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python -m adas.telegram_digest --cache adas/test_sets/video_cache_w1.json
```

Send the Step 11 digest to Telegram:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python -m adas.telegram_digest --cache adas/test_sets/video_cache_w1.json --send
```

Capture Step 12 Telegram reactions as feedback:

```bash
cd /home/shishirmishra/Learnings/EvoClaw
.venv/bin/python -m adas.telegram_feedback \
  --delivery-log skills/youtube-curator/delivery_log.json \
  --feedback adas/test_sets/feedback.json
```

React up or down to an individual video message in Telegram, then run the above. Offset state is persisted so repeated runs only process new reactions.
