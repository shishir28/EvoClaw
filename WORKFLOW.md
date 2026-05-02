# EvoClaw workflow

This file explains **what actually happens today** in the codebase, and **what the future full loop is supposed to look like**.

## 1. Current runnable workflow

Today, EvoClaw supports a complete **fetch -> evaluate** workflow.

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

`adas/evaluator_loader.py`:

1. reads a candidate `SKILL.md`
2. parses its YAML frontmatter
3. loads cached videos from JSON
4. loads optional feedback history from `feedback.json`
5. assembles an `EvaluationRequest`

### Step 3: Select videos for the skill

`adas/skill_executor.py`:

1. reads the skill strategy from the parsed skill metadata
2. chooses the matching Python strategy executor
3. applies that strategy over the cached video records
4. returns selected video IDs plus execution notes

Supported strategies today:

- `recency`
- `engagement-velocity`
- `llm-substance-judge`

### Step 4: Score the selection

`adas/evaluator.py` coordinates two scoring paths.

#### 4a. Algorithmic scoring

`adas/algorithmic_scorer.py` scores:

- `freshness`
- `diversity`
- `alignment`

`alignment` is still a lightweight placeholder that becomes neutral when there is no feedback history.

#### 4b. Optional LLM judging

If LLM judging is enabled, `adas/llm_judge.py` scores:

- `relevance`
- `substance`
- `reasoning`

It builds a prompt from `adas/prompts/eval_judge.md` and calls the configured OpenAI-compatible endpoint.

### Step 5: Aggregate the result

`adas/evaluator.py`:

1. applies all dimension scores to the result
2. checks whether any dimensions are still missing
3. returns `partially_scored` if only algorithmic dimensions are present
4. returns `scored` with `total_score` once all dimensions are available

## 2. Current workflow as a diagram

```text
SKILL.md + cache JSON + feedback JSON
                |
                v
      evaluator_loader.py
                |
                v
        EvaluationRequest
                |
                v
         skill_executor.py
                |
                v
      selected_video_ids + notes
                |
                v
      algorithmic_scorer.py ----> llm_judge.py (optional)
                \                  /
                 \                /
                  v              v
                    evaluator.py
                        |
                        v
                 EvaluationResult
```

## 3. What is not in the workflow yet

The following steps are still planned, not implemented:

1. save evaluated results into archive folders
2. generate new candidate skills through `adas/meta_agent.py`
3. compare candidates against archived history
4. deploy the winning skill automatically
5. run the production skill on a schedule
6. send the digest to Telegram
7. capture Telegram reactions back into feedback history

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

## 6. Immediate next workflow milestone

The next useful workflow to add is:

1. run all three baselines on the same cached dataset
2. persist each evaluation result
3. compare the scores side by side
4. confirm the evaluator ranking feels sensible

That is the last missing step before archive work becomes worth building.
