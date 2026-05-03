# EvoClaw implementation checklist

This file is the practical companion to `Plan.md`.

Use it to answer two questions quickly:

1. **What already exists?**
2. **What should we build next, step by step?**

It is written as a learning-oriented checklist so you can follow the system incrementally and understand how each part fits together.
---

## 1. Current implementation status

### Already implemented

- [x] `adas/youtube_fetcher.py`
- [x] fetcher updated for the installed `youtube-transcript-api` client
- [x] `subscriber_count` enrichment in fetcher output
- [x] `adas/config.py`
- [x] `adas/evaluator.py` orchestration flow
- [x] `adas/evaluation/loader.py`
- [x] `adas/evaluation/models.py`
- [x] `adas/evaluation/scorer.py`
- [x] `adas/evaluation/judge.py`
- [x] `adas/evaluation/executor.py`
- [x] `adas/baseline/catalog.py`
- [x] `adas/baseline/models.py`
- [x] `adas/baseline/runner.py`
- [x] `adas/baseline/result_store.py`
- [x] `adas/baseline_comparison.py`
- [x] `adas/archive_runtime/models.py`
- [x] `adas/archive_runtime/store.py`
- [x] `adas/archive_runtime/service.py`
- [x] `adas/prompts/eval_judge.md`
- [x] baseline skills in `adas/baselines/`
- [x] production skill placeholder in `skills/youtube-curator/SKILL.md`
- [x] populated archive index in `adas/archive/index.json`
- [x] versioned archive entries under `adas/archive/skill_*/`
- [x] sample cache in `adas/test_sets/video_cache_test.json`
- [x] reusable local cache in `adas/test_sets/video_cache_w1.json`
- [x] feedback history stub in `adas/test_sets/feedback.json`
- [x] cron config stub in `cron/jobs.json`
- [x] repository documentation in `README.md` files
- [x] high-level orientation docs in `ARCHITECTURE.md` and `WORKFLOW.md`
- [x] unit tests for evaluator, loader, scorer, executor, evaluator CLI helpers, and Step 5 comparison flow
- [x] current full pytest suite passing (`147 passed`)

### Not implemented yet

- [ ] `adas/meta_agent.py`
- [ ] generated archive entries under `adas/archive/skill_*`
- [ ] automatic deployment of winning skill
- [ ] Telegram digest sender
- [ ] Telegram reaction capture / feedback ingestion automation
- [ ] actual scheduled runtime wiring
- [ ] NemoClaw policy configuration in runnable form

---

## 2. How the full system is supposed to work

The planned end-to-end flow is:

1. Fetch candidate YouTube videos.
2. Run a skill or strategy to select the best 3.
3. Score that skill on relevance, substance, freshness, diversity, reasoning, and alignment.
4. Store the skill and its results in the archive.
5. Let a meta agent propose improved skills.
6. Promote the best skill into `skills/youtube-curator/SKILL.md`.
7. Run the production skill on a schedule.
8. Send the results to Telegram.
9. Capture feedback and feed it back into scoring.

---

## 3. Step-by-step implementation roadmap

## Step 1 - Finish the foundation

**Goal:** make the existing fetcher work against real data and produce a reliable evaluation dataset.

### Tasks

- [x] add a real `YOUTUBE_API_KEY` in `.env`
- [x] run `adas/youtube_fetcher.py` successfully
- [x] inspect the cache output and confirm the fields are usable
- [x] decide the canonical cache filenames to use (`video_cache_w1.json` for the first reusable set)
- [x] create one solid dataset with roughly 30-50 videos
- [x] review the three baseline strategies against that dataset

### Why this matters

Everything downstream depends on clean cached video data.

### Step 1 result

Step 1 is effectively complete for learning and implementation purposes.

Current dataset notes:

- `video_cache_w1.json` contains 49 videos
- cache entries now include `views_per_hour` and `subscriber_count`
- transcripts are **best-effort**, not guaranteed for every video
- missing transcripts should fall back to `description` in future evaluator logic

### Files involved

- `adas/youtube_fetcher.py`
- `adas/config.py`
- `.env`
- `adas/test_sets/`

---

## Step 2 - Build the evaluator skeleton

**Goal:** create the scoring engine before worrying about the meta-agent loop.

### Tasks

- [x] create `adas/evaluator.py`
- [x] define evaluator input shape
- [x] define evaluator output shape
- [x] load `SKILL.md`
- [x] load cached videos
- [x] load optional feedback history
- [x] implement weighted score aggregation
- [x] implement algorithmic scoring first:
  - [x] freshness
  - [x] diversity
  - [x] alignment placeholder

### Why this matters

The evaluator defines what "better" means. Without it, the meta agent has nothing useful to optimize.

### Step 2 progress

Step 2 is complete for the current implementation scope.

The evaluator now has:

- request models for skill, videos, and feedback history
- result models for weighted dimensions and final output shape
- a dedicated loader module for `SKILL.md`, cache JSON, and optional feedback JSON
- a smaller, more cohesive structure:
  - `adas/evaluation/models.py` for DTO-style data contracts
  - `adas/evaluation/loader.py` for request assembly
  - `adas/evaluator.py` for orchestration
  - `adas/evaluation/scorer.py` for rule-based scoring
  - `adas/evaluation/judge.py` for model-based judging
- weighted aggregation once dimension scores are assigned
- algorithmic scoring for freshness, diversity, and a neutral-feedback alignment placeholder
- `score()` orchestration for explicit selected video IDs
- a CLI path that now returns a real scored result even without explicit selected IDs
- LLM-judged scoring for relevance, substance, and reasoning
- lazy default LLM judge construction so non-LLM runs avoid eager model client setup
- a result template and execution hooks for end-to-end evaluator scoring

Current limitation:

- real OpenClaw execution is still a later replacement step

### Files involved

- `adas/evaluator.py`
- `adas/config.py`
- `adas/test_sets/feedback.json`

---

## Step 3 - Define how a skill gets executed

**Goal:** decide how a `SKILL.md` becomes actual picks plus reasoning.

### Tasks

- [x] define the execution contract for a skill
- [x] choose the first implementation approach:
  - [x] Python adapter for baseline skills
  - [ ] later replacement with real OpenClaw execution
- [x] make the evaluator consume that contract
- [x] keep the interface generic enough to swap implementations later

### Why this matters

A skill cannot be scored until it can produce structured output.

### Step 3 progress

Step 3 is complete for the current implementation path.

The evaluator can now execute the current baseline-style skills automatically through a Python adapter:

- `adas/evaluation/executor.py` implements deterministic baseline execution
- strategy-specific executors are registered behind a registry-driven adapter
- `Evaluator.score(...)` can auto-select top videos for supported strategies
- the execution layer is separate from scoring so it can later be replaced with real OpenClaw execution

### Files involved

- `adas/evaluator.py`
- potentially a new adapter module under `adas/`
- `adas/baselines/*.md`

---

## Step 4 - Add LLM judging

**Goal:** score the subjective dimensions using the configured inference backend.

### Tasks

- [x] create `adas/prompts/eval_judge.md`
- [x] add model client logic
- [x] implement judge calls for:
  - [x] relevance
  - [x] substance
  - [x] reasoning
- [x] parse JSON responses safely
- [x] combine judge scores with algorithmic scores

### Why this matters

This is what lets the system judge quality, not just recency or popularity.

### Step 4 progress

Step 4 is complete for the current implementation scope.

The evaluator can now:

- load `adas/prompts/eval_judge.md`
- call the configured local OpenAI-compatible endpoint
- separate prompt loading and chat transport behind injectable adapters
- score `relevance`, `substance`, and `reasoning`
- merge those scores into the existing algorithmic evaluator flow
- return a fully aggregated `total_score` when all dimensions are present

### Files involved

- `adas/evaluator.py`
- `adas/prompts/eval_judge.md`
- `adas/config.py`

---

## Step 5 - Score the three baselines end to end

**Goal:** verify that the evaluator behaves sensibly before building the meta agent.

### Tasks

- [x] run all three baselines on the same dataset
- [x] save result breakdowns
- [x] compare the baseline scores
- [x] confirm the differences make intuitive sense
- [x] tune weights only if clearly necessary

### Why this matters

If the evaluator is wrong, the rest of the system will optimize toward the wrong target.

### Step 5 progress

Step 5 is complete for the current implementation scope.

Saved outputs now live under:

- `adas/baseline_results/video_cache_w1/summary.json`
- `adas/baseline_results/video_cache_w1/results/`

Current recorded ranking on `video_cache_w1.json`:

1. `recency-first` — `7.3924`
2. `engagement-velocity` — `7.1419`
3. `llm-substance-judge` — `5.7784`

Interpretation:

- the ranking is plausible for the current evaluator and dataset
- recency and engagement-velocity are close, which makes sense because they share two strong picks
- the substance proxy baseline scores lower because its current heuristic picks do not hold up as strongly under the LLM judge
- no weight tuning was applied yet, because the result did not look obviously wrong
- baseline comparison now also fails fast when the required cache input is missing, while keeping feedback optional

### Files involved

- `adas/baselines/*.md`
- `adas/evaluator.py`
- `adas/baseline_results/`
- `adas/test_sets/`

---

## Step 6 - Build the archive layer

**Goal:** store every evaluated skill in a form the system can learn from later.

### Tasks

- [x] define archive entry structure
- [x] create `archive/skill_xxx/` folders
- [x] save:
  - [x] `SKILL.md`
  - [x] `result.json`
  - [x] `meta.json`
- [x] update `adas/archive/index.json`
- [x] track `best_skill_id`
- [x] track `best_score`

### Why this matters

The archive is the memory of the improvement loop.

### Files involved

- `adas/archive/index.json`
- generated `adas/archive/skill_xxx/`
- `adas/archive_runtime/models.py`
- `adas/archive_runtime/store.py`
- `adas/archive_runtime/service.py`
- `adas/baseline_comparison.py`

---

## Step 7 - Build feedback ingestion

**Goal:** make `feedback.json` meaningful before wiring Telegram automation.

### Tasks

- [ ] define the final feedback schema clearly
- [ ] add a simple manual way to append feedback
- [ ] update evaluator alignment scoring to read it
- [ ] start with a lightweight heuristic for alignment

### Why this matters

This separates preference learning from Telegram integration and keeps iteration simple.

### Files involved

- `adas/test_sets/feedback.json`
- `adas/evaluator.py`

---

## Step 8 - Create meta-agent prompts

**Goal:** define the prompt assets before writing the orchestration code.

### Tasks

- [ ] create `adas/prompts/meta_system.md`
- [ ] create `adas/prompts/meta_design.md`
- [ ] create `adas/prompts/meta_reflect.md`
- [ ] define the JSON output contract:
  - [ ] `thought`
  - [ ] `name`
  - [ ] `skill_md`
- [ ] define reflection checks for novelty and correctness
- [ ] define debug instructions for broken outputs

### Why this matters

Good prompt contracts make the loop much easier to build and debug.

### Files involved

- `adas/prompts/`

---

## Step 9 - Build `meta_agent.py`

**Goal:** implement one complete generate -> reflect -> evaluate -> archive cycle.

### Tasks

- [ ] create `adas/meta_agent.py`
- [ ] load archive history
- [ ] generate a candidate skill
- [ ] run one or two reflection passes
- [ ] validate candidate format
- [ ] evaluate the candidate
- [ ] archive the result
- [ ] update best skill metadata

### Why this matters

This is the actual ADAS loop.

### Files involved

- `adas/meta_agent.py`
- `adas/evaluator.py`
- `adas/archive/`
- `adas/prompts/`

---

## Step 10 - Add production skill deployment

**Goal:** automatically promote the best archived skill to the live skill path.

### Tasks

- [ ] copy winning `SKILL.md` to `skills/youtube-curator/SKILL.md`
- [ ] only deploy when the new score is better
- [ ] record which skill version was deployed

### Why this matters

This is how experimentation becomes production behavior.

### Files involved

- `adas/meta_agent.py`
- `skills/youtube-curator/SKILL.md`

---

## Step 11 - Add Telegram delivery

**Goal:** send the production results to Telegram.

### Tasks

- [ ] create a Telegram sender module
- [ ] define the final message formatter
- [ ] run the production skill and format its picks
- [ ] send a manual test message

### Why this matters

This is the user-facing output of the system.

### Files involved

- new Telegram integration code
- `skills/youtube-curator/SKILL.md`
- `.env`

---

## Step 12 - Add Telegram feedback capture

**Goal:** feed real reactions back into the system.

### Tasks

- [ ] choose polling or webhook
- [ ] map reactions back to delivered video IDs
- [ ] persist results into `adas/test_sets/feedback.json`
- [ ] connect those results to evaluator alignment scoring

### Why this matters

This closes the human-feedback loop.

### Files involved

- new Telegram feedback code
- `adas/test_sets/feedback.json`
- `adas/evaluator.py`

---

## Step 13 - Wire cron and runtime automation

**Goal:** make the full loop run on schedule.

### Tasks

- [ ] verify `cron/jobs.json` matches real file paths
- [ ] make missing-config failures explicit
- [ ] run the evolution job manually
- [ ] run the digest job manually
- [ ] only then trust scheduled execution

### Why this matters

Scheduling should happen only after each manual path works.

### Files involved

- `cron/jobs.json`
- `adas/meta_agent.py`
- Telegram delivery code

---

## Step 14 - Add hardening and policy configuration

**Goal:** make the system safe, stable, and suitable for real repeated execution.

### Tasks

- [ ] apply network policy for YouTube, Telegram, and local inference
- [ ] confirm writable paths are limited to intended workspace locations
- [ ] add validation for generated `SKILL.md`
- [ ] add retry handling for model and API failures
- [ ] add useful logs around archive writes, deployment, and delivery

### Why this matters

This is what turns a prototype into a dependable system.

---

## 4. Recommended learning order

If the goal is to understand what is happening as you build, use this order:

- [x] Step 1 - real fetch + cache generation
- [x] Step 2 - evaluator skeleton
- [x] Step 3 - skill execution contract
- [x] Step 4 - LLM judging
- [x] Step 5 - baseline scoring runs
- [x] Step 6 - archive writes
- [ ] Step 7 - feedback ingestion
- [ ] Step 8 - meta-agent prompts
- [ ] Step 9 - meta-agent loop
- [ ] Step 10 - deployment
- [ ] Step 11 - Telegram sending
- [ ] Step 12 - Telegram feedback capture
- [ ] Step 13 - cron automation
- [ ] Step 14 - hardening

---

## 5. Smallest useful milestone

If we want the smallest checkpoint that proves the project is moving in the right direction, aim for this:

- [x] fetch real video data
- [x] build one reusable cached dataset
- [x] execute the three baseline strategies
- [x] score them with the evaluator
- [x] store the results in the archive

Once this milestone works, the rest of the project becomes much easier to reason about.
