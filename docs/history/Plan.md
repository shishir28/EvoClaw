# ADAS on NemoClaw: AI+Startup YouTube Curator

## Project overview

This is the original design plan. For current implementation status, prefer `README.md`, `WORKFLOW.md`, `ARCHITECTURE.md`, and `cron/README.md`.

A self-evolving video curation system that runs inside NemoClaw's sandboxed environment. Every morning, your OpenClaw agent sends you the top 3 YouTube videos on AI + entrepreneurship via Telegram. Behind the scenes, a Meta Agent Search loop runs overnight to continuously discover better curation strategies — expressed as OpenClaw SKILL.md files — and deploys the winners automatically.

The system combines three ideas:

- **Meta Agent Search** (from the ADAS paper) for automatically discovering better agent skills
- **NemoClaw's sandbox** for safe execution of untested, auto-generated skills
- **OpenClaw's skill system** as the interface between discovered strategies and the running agent

## Implemented areas

The codebase has moved beyond the original planning stage. Current implemented areas include:

- real YouTube fetches work and produce reusable caches
- the evaluator is implemented and split into focused modules
- baseline `SKILL.md` files can be executed through a Python adapter over cached videos
- LLM judging for relevance, substance, and reasoning is implemented
- Step 5 baseline comparison is implemented and persists JSON results plus a ranking summary
- Step 6 archive persistence is implemented and now writes `SKILL.md`, `result.json`, `meta.json`, plus best-skill metadata under `adas/archive/`
- Step 7 feedback persistence is implemented and now stores feedback entries under `adas/test_sets/feedback.json` with reusable video snapshots for alignment scoring
- Step 9 meta-agent orchestration is implemented and can build prompt context, generate a candidate, run reflection passes, validate it locally, evaluate it, and archive it
- Step 10 skill promotion is implemented and can copy the archive winner into `skills/youtube-curator/SKILL.md` when it beats the recorded production deployment
- evaluator CLI defaults now run a real scoring flow, default LLM judge setup is lazy, and baseline comparison validates the required cache input up front
- Telegram delivery, per-video reaction capture, cache refresh, and scheduled runtime wiring are implemented.

Remaining major adapter gap: real OpenClaw execution.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  NemoClaw Sandbox (OpenShell)                               │
│  Network + filesystem isolation, policy enforcement         │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Meta Agent (is launched nightly by the external NemoClaw/OpenShell scheduler)                   │  │
│  │  Reads archive → designs new SKILL.md → self-reflects │  │
│  └──────────┬──────────────────────────┬─────────────────┘  │
│             │ writes new skill         │ reads history       │
│             ▼                          │                     │
│  ┌────────────────────┐    ┌───────────┴──────────┐         │
│  │  Evaluation Harness│    │  Skill Archive       │         │
│  │  Scores skill on   │───▶│  SKILL.md + scores   │         │
│  │  cached video sets │    │  Stepping stones     │         │
│  └────────┬───────────┘    └──────────────────────┘         │
│           │ loads skill into                                 │
│           ▼                                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  OpenClaw Agent                                       │  │
│  │  Runs candidate skill → fetches YouTube → ranks       │  │
│  │  Nemotron local inference (Ollama)                     │  │
│  └──────────┬────────────────────────┬───────────────────┘  │
│             │                        │                       │
│             ▼                        ▼                       │
│  ┌──────────────────┐    ┌──────────────────┐               │
│  │  Telegram         │    │  External Scheduler  │               │
│  │  Daily delivery   │    │  Overnight ADAS  │               │
│  │  + feedback (👍👎) │    │  evolution loop  │               │
│  └──────────────────┘    └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## Target project structure

```
~/.openclaw/workspace/
├── skills/
│   └── youtube-curator/
│       └── SKILL.md              ← The "production" skill (best from archive)
│
├── adas/
│   ├── baseline_comparison.py    ← Step 5 comparison orchestration and CLI
│   ├── baseline_results/         ← Saved Step 5 comparison outputs
│   ├── config.py                 ← Topics, scoring weights, model config
│   ├── evaluator.py              ← Evaluator orchestration
│   ├── feedback_cli.py           ← Step 7 manual feedback append CLI
│   ├── youtube_fetcher.py        ← YouTube search + metadata extraction
│   ├── meta_agent.py             ← Step 9 meta-agent CLI
│   │
│   ├── deployment/
│   │   └── promoter.py           ← Step 10 production skill promotion
│   │
│   ├── archive_runtime/
│   │   ├── models.py             ← Step 6 archive DTOs
│   │   ├── service.py            ← Step 6 archive orchestration
│   │   └── store.py              ← Step 6 archive persistence
│   │
│   ├── baseline/
│   │   ├── catalog.py            ← Ordered baseline skill discovery
│   │   ├── comparison.py         ← Step 5 comparison core flow
│   │   ├── models.py             ← Step 5 result contracts
│   │   ├── result_store.py       ← Step 5 persistence layer
│   │   └── runner.py             ← Multi-skill evaluation orchestration
│   │
│   ├── archive/
│   │   ├── index.json            ← Best-skill metadata + archive registry
│   │   ├── skill_001/            ← Archived evaluated skill entry
│   │   │   ├── SKILL.md
│   │   │   ├── result.json       ← Saved evaluation record
│   │   │   └── meta.json         ← Archive metadata + evaluation context
│   │   ├── skill_002/            ← Archived evaluated skill entry
│   │   │   └── ...
│   │   └── ...
│   │
│   ├── baselines/
│   │   ├── baseline_recency.md   ← Seed skill 1: sort by recency
│   │   ├── baseline_popular.md   ← Seed skill 2: sort by view velocity
│   │   └── baseline_curated.md   ← Seed skill 3: LLM judges substance
│   │
│   ├── evaluation/
│   │   ├── executor.py           ← Python adapter for baseline skills
│   │   ├── judge.py              ← Prompt-based semantic judging
│   │   ├── loader.py             ← Loads skill/cache/feedback inputs
│   │   ├── models.py             ← DTO-style evaluator contracts
│   │   ├── scorer.py             ← Deterministic scoring dimensions
│   │   └── service.py            ← Evaluator orchestration
│   │
│   ├── feedback/
│   │   ├── service.py            ← Step 7 feedback append flow
│   │   └── store.py              ← Step 7 feedback persistence
│   │
│   ├── meta/
│   │   ├── client.py             ← Meta-agent chat client wrapper
│   │   ├── context.py            ← Archive + feedback prompt context builder
│   │   ├── dedupe.py             ← Duplicate-skill detection
│   │   ├── generator.py          ← Candidate generation over Step 8 prompts
│   │   ├── loop.py               ← Generate → reflect → evaluate → archive orchestration
│   │   ├── parser.py             ← Candidate JSON/frontmatter validation
│   │   └── reflector.py          ← Candidate reflection and repair
│   │
│   ├── test_sets/
│   │   ├── video_cache_w1.json   ← Cached YouTube results for eval
│   │   └── feedback.json         ← Your 👍/👎 history, stored as {"history":[...]}
│   │
│   └── prompts/
│       ├── eval_judge.md         ← LLM-as-judge prompt for scoring
│       ├── meta_system.md        ← Shared system contract for meta-agent outputs
│       ├── meta_design.md        ← Candidate skill design prompt
│       └── meta_reflect.md       ← Candidate reflection and repair prompt
│
└── cron/
    └── jobs.json                 ← Cron entries for ADAS + daily delivery
```

---

## Component details

### Component 1: Baseline skills (3 seed SKILL.md files)

These are hand-written starting points that the meta agent will build on. Each takes a different approach to the same problem.

**Baseline A — "Recency first"**
Strategy: Fetch videos from the last 48 hours, filter to AI + startups topic, sort by recency, pick top 3. Simple but catches breaking content.

**Baseline B — "Engagement velocity"**
Strategy: Fetch videos from the last 7 days, compute views-per-hour since publish, filter out channels with fewer than 10K subscribers (quality floor), pick the 3 with the highest velocity. Favors videos that are gaining traction fast.

**Baseline C — "LLM substance judge"**
Strategy: Fetch 20 candidate videos from the last 7 days, extract descriptions and (when available) auto-generated transcripts, ask Nemotron to rate each on a 1-10 "substance score" based on whether it contains actionable insights vs. hype, pick top 3. Slower but finds hidden gems from smaller channels.

Each baseline will be a complete SKILL.md file with YAML frontmatter and step-by-step instructions that OpenClaw can follow.

---

### Component 2: YouTube fetcher (youtube_fetcher.py)

A Python utility that handles YouTube data collection. This runs inside the sandbox so network access needs to be policy-approved.

**Capabilities:**
- Search YouTube Data API v3 for videos matching query terms
- Extract metadata: title, channel, publish date, views, likes, duration, description
- Fetch auto-generated captions/transcript when available (via youtube-transcript-api)
- Cache results to disk so the evaluation harness can replay without hitting the API

**Network policy requirements:**
- Allow egress to `www.googleapis.com` (YouTube Data API)
- Allow egress to `youtube.com` (transcript fetching)
- API key stored in NemoClaw environment config

**Rate limiting:**
- YouTube API quota is 10,000 units/day
- Each search costs 100 units, each video detail costs 1 unit
- Budget: ~50 searches + 500 video details per day (plenty for ADAS + daily delivery)

---

### Component 3: Evaluation harness (evaluator.py)

Scores a candidate SKILL.md against cached video sets. This is the critical piece that makes the ADAS loop work.

**Inputs:**
- A candidate SKILL.md file
- A cached set of 30-50 YouTube videos with full metadata
- (Optional) historical feedback from your Telegram reactions

**Scoring dimensions (each 0-10, weighted):**

| Dimension | Weight | How scored |
|-----------|--------|------------|
| Relevance | 0.25 | LLM-as-judge: are all 3 picks genuinely about AI + entrepreneurship? |
| Substance | 0.25 | LLM-as-judge: does the video offer real insights vs. clickbait/hype? |
| Freshness | 0.15 | Algorithmic: published within last 7 days? Bonus for last 48 hours. |
| Diversity | 0.15 | Algorithmic: different channels? Different sub-topics? |
| Reasoning | 0.10 | LLM-as-judge: does the "why watch" summary accurately reflect content? |
| Alignment | 0.10 | Feedback match: does the pick pattern align with your 👍 history? |

**Current process:**
1. Load the candidate `SKILL.md`, cached video set, and optional feedback history
2. Resolve picks either from explicit selected video IDs or from the Python baseline adapter
3. Score algorithmic dimensions (`freshness`, `diversity`, `alignment`)
4. Optionally call the LLM judge for `relevance`, `substance`, and `reasoning`
5. Compute the weighted total (0-10 scale) when all dimensions are present
6. Return scores plus the detailed breakdown

**Later replacement step:**
- Swap the Python adapter for real OpenClaw skill execution when the surrounding runtime exists

**Why LLM-as-judge works here:**
The ADAS paper showed that LLM-as-judge ensembles are effective even with modest correlation to ground truth, as long as they're complementary. We use Nemotron locally for all judging — no API costs, full privacy.

---

### Component 4: Meta agent loop (meta_agent.py)

The first Step 9 version now exists as a local CLI-driven loop. It is not yet the final overnight production workflow, but it already performs the core single-run sequence:

1. build archive + feedback prompt context
2. generate one candidate
3. run one or more reflection passes
4. validate the candidate locally
5. evaluate it with the existing evaluator
6. archive the result

The production form now has external scheduling wiring and Telegram delivery; multi-iteration operational hardening remains ongoing.

**Configuration:**
- Iterations per night: 5 (start conservative, increase as you gain confidence)
- Meta agent model: Nemotron 3 Super via Ollama (you have DGX Spark)
- Max self-reflection rounds: 2 (per the paper)
- Max debug retries on error: 3

**Current local-loop pseudocode:**

```
context = build_context(archive, feedback)
candidate = generator.generate(context)

for round in range(reflect_passes):
    reflection = reflector.reflect(candidate, context)
    candidate = reflection.candidate
    if reflection.verdict == "accept":
        break

validate_candidate(candidate)

if not is_duplicate(candidate.skill_md, archive):
    write temp skill file
    scores = evaluator.score(candidate, test_set)
    archive_service.archive_records(...)
```

**Meta agent prompt structure:**

The meta agent receives:
- Framework description (what a SKILL.md is, what tools are available)
- The full archive (all previous skills + their scores + design rationale)
- Instructions to be creative, build on stepping stones, think outside the box
- Output format: JSON with thought, name, and skill_md fields

The self-reflection prompts check for:
- Is this actually different from existing skills in the archive?
- Are there implementation mistakes (bad YAML, unclear instructions)?
- Can the strategy be improved without changing the overall design?

---

### Component 5: Telegram delivery + feedback loop

**Morning delivery (current external schedule sends at 4:30 AM local time):**

The production skill (best from archive) runs and sends a Telegram message like:

```
🎬 Your AI + startup picks for today

1. "How I Built a $2M ARR AI Tool in 6 Months"
   @IndieHackerAI · 18 min · 2 days ago
   🔗 https://youtube.com/watch?v=xxx
   → Practical breakdown of pricing, distribution, and
     the specific AI APIs used. No fluff.

2. "Why 90% of AI Startups Will Fail in 2026"
   @FirstRoundCapital · 24 min · 1 day ago
   🔗 https://youtube.com/watch?v=yyy
   → Partner at First Round shares patterns from their
     portfolio. Data-heavy, contrarian take.

3. "Building AI Agents That Sell Themselves"
   @LennysPodcast · 32 min · 3 days ago
   🔗 https://youtube.com/watch?v=zzz
   → Interview with founder of [company]. Covers
     go-to-market for agent-based products.

React 👍 or 👎 to each to help me improve picks.
```

**Feedback collection:**

- You react to the Telegram message with 👍 or 👎 (or ignore)
- A webhook or polling script captures your reactions
- Reactions are stored in `test_sets/feedback.json` as:
  ```json
  {
    "history": [
      {
        "date": "2026-04-29",
        "picks": [
          {"video_id": "xxx", "reaction": "up", "skill_version": "skill_012"},
          {"video_id": "yyy", "reaction": "down", "skill_version": "skill_012"},
          {"video_id": "zzz", "reaction": null, "skill_version": "skill_012"}
        ]
      }
    ]
  }
  ```
- Each stored pick can also include a lightweight `snapshot` of the video metadata so later alignment scoring can compare new candidates to prior liked/disliked picks even when only the historical feedback file is available.
- The evaluation harness uses this feedback for the "alignment" scoring dimension
- Over time, the meta agent learns patterns: you prefer tactical/practical over thought-leadership, short over long, etc.

---

### Component 6: External schedule source

`cron/jobs.json` is the authoritative job catalog. NemoClaw/OpenShell reads it and launches:

- `refresh-video-cache` at 00:30
- `adas-evolution` at 01:30
- `morning-digest` at 04:30
- `reaction-capture` at 08:30
- `daily-status` at 09:00

## NemoClaw security configuration

**Network policy (nemoclaw-blueprint):**

```yaml
egress_rules:
  - name: youtube-api
    destination: "www.googleapis.com"
    ports: [443]
    action: allow
    reason: "YouTube Data API v3 for video search and metadata"

  - name: youtube-transcripts
    destination: "youtube.com"
    ports: [443]
    action: allow
    reason: "Fetch auto-generated captions for substance scoring"

  - name: ollama-local
    destination: "127.0.0.1"
    ports: [11434]
    action: allow
    reason: "Local Nemotron inference via Ollama"

  - name: telegram-api
    destination: "api.telegram.org"
    ports: [443]
    action: allow
    reason: "Send daily digest and receive feedback"

  default_action: deny
```

**Filesystem policy:**
- Read/write: `~/.openclaw/workspace/adas/` (archive, test sets, feedback)
- Read/write: `~/.openclaw/workspace/skills/youtube-curator/` (deploy winners)
- Read-only: everything else

---

## Implementation phases

### Phase 1: Foundation (day 1-2)
- [x] Set up YouTube Data API key and test basic search
- [x] Build `youtube_fetcher.py` with search + metadata + transcript extraction
- [x] Cache 1 week of video results for evaluation
- [x] Write the 3 baseline SKILL.md files
- [ ] Test that each baseline works manually via OpenClaw + Telegram

### Phase 2: Evaluation harness (day 3-4)
- [x] Build `evaluator.py` with all 6 scoring dimensions
- [x] Split evaluator concerns into loader, DTO, scorer, judge, and executor modules
- [x] Write the LLM-as-judge prompts for relevance, substance, and reasoning
- [x] Score all 3 baselines against the cached video set
- [x] Verify scores are sensible (baselines should score differently)
- [ ] Build the feedback ingestion from Telegram reactions

### Phase 3: Meta agent loop (day 5-7)
- [x] Write meta agent prompts (design, reflect, debug)
- [x] Build the first local `meta_agent.py` loop
- [ ] Run 5 iterations manually, inspect generated skills
- [ ] Verify archive grows correctly with scores and metadata
- [x] Test auto-deployment of winning skill

### Phase 4: Automation and feedback (day 8-10)
- [x] Configure cron jobs from `cron/jobs.json` (cache refresh, evolution, 4:30 AM delivery, reaction capture)
- [x] Set up Telegram reaction capture for feedback loop
- [ ] Configure NemoClaw network policies
- [ ] Run the full system for 3 days, monitor logs
- [ ] Tune scoring weights based on early results

### Phase 5: Iterate and improve (ongoing)
- [ ] Review archive weekly — look for interesting stepping stones
- [ ] Increase iterations per night as confidence grows (5 → 10 → 15)
- [ ] Add new video sources beyond YouTube search (channel subscriptions, playlist monitoring)
- [ ] Consider multi-objective scoring (substance vs. brevity vs. novelty)
- [ ] Share findings with NemoClaw/OpenClaw community

---

## Key risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| YouTube API quota exhaustion | No new data for eval | Cache aggressively, limit to 50 searches/day |
| Meta agent generates broken SKILL.md | Eval fails, wasted iteration | 3 debug retries + YAML validation before eval |
| All skills converge on same strategy | No diversity, no improvement | Novelty check in self-reflection, archive diversity bonus |
| Nemotron too weak for LLM-as-judge | Bad scores, bad evolution | Start with Nemotron Super 120B on DGX Spark; fall back to cloud API if needed |
| Feedback loop is too slow | Takes weeks to see preference signal | Start with automated proxy scores only, add feedback as bonus signal |

---

## Success metrics

After 2 weeks of running:

- **Archive size**: 30+ discovered skills (5/night × 7 nights, accounting for some failures)
- **Score improvement**: Best skill scores at least 20% higher than the best baseline
- **Daily satisfaction**: You 👍 at least 2 of 3 picks on most days
- **Novel strategies**: At least 3 qualitatively different approaches emerged that you wouldn't have thought of

After 1 month:

- **Stepping stones visible**: Later skills clearly build on earlier discoveries
- **Feedback alignment**: Skills that score high on automated metrics also get more 👍 from you
- **Transfer potential**: Best skill's strategy could be adapted to other curation tasks (papers, newsletters, podcasts)
