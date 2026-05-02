# ADAS on NemoClaw: AI+Startup YouTube Curator

## Project overview

A self-evolving video curation system that runs inside NemoClaw's sandboxed environment. Every morning, your OpenClaw agent sends you the top 3 YouTube videos on AI + entrepreneurship via Telegram. Behind the scenes, a Meta Agent Search loop runs overnight to continuously discover better curation strategies — expressed as OpenClaw SKILL.md files — and deploys the winners automatically.

The system combines three ideas:

- **Meta Agent Search** (from the ADAS paper) for automatically discovering better agent skills
- **NemoClaw's sandbox** for safe execution of untested, auto-generated skills
- **OpenClaw's skill system** as the interface between discovered strategies and the running agent

## Current implementation snapshot

The codebase is currently at the **working fetcher + evaluator** stage:

- real YouTube fetches work and produce reusable caches
- the evaluator is implemented and split into focused modules
- baseline `SKILL.md` files can be executed through a Python adapter over cached videos
- LLM judging for relevance, substance, and reasoning is implemented
- archive writes, meta-agent orchestration, Telegram automation, and scheduled runtime wiring are still future phases

The immediate next milestone is to run all three baselines end to end on the same dataset, save the score breakdowns, and confirm the evaluator ranking makes sense.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  NemoClaw Sandbox (OpenShell)                               │
│  Network + filesystem isolation, policy enforcement         │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Meta Agent (runs nightly via cron)                   │  │
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
│  │  Telegram         │    │  Cron Scheduler  │               │
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
│   ├── algorithmic_scorer.py     ← Deterministic scoring dimensions
│   ├── config.py                 ← Topics, scoring weights, model config
│   ├── evaluator.py              ← Evaluator orchestration
│   ├── evaluator_loader.py       ← Loads skill/cache/feedback inputs
│   ├── evaluator_models.py       ← DTO-style evaluator contracts
│   ├── llm_judge.py              ← Prompt-based semantic judging
│   ├── skill_executor.py         ← Python adapter for baseline skills
│   ├── youtube_fetcher.py        ← YouTube search + metadata extraction
│   ├── meta_agent.py             ← Main ADAS loop (planned)
│   │
│   ├── archive/
│   │   ├── index.json            ← Registry stub for discovered skills + scores
│   │   ├── skill_001/             ← Planned generated archive entry
│   │   │   ├── SKILL.md
│   │   │   ├── result.json       ← Evaluation scores
│   │   │   └── meta.json         ← Design rationale from meta agent
│   │   ├── skill_002/             ← Planned generated archive entry
│   │   │   └── ...
│   │   └── ...
│   │
│   ├── baselines/
│   │   ├── baseline_recency.md   ← Seed skill 1: sort by recency
│   │   ├── baseline_popular.md   ← Seed skill 2: sort by view velocity
│   │   └── baseline_curated.md   ← Seed skill 3: LLM judges substance
│   │
│   ├── test_sets/
│   │   ├── video_cache_w1.json   ← Cached YouTube results for eval
│   │   └── feedback.json         ← Your 👍/👎 history from Telegram
│   │
│   └── prompts/
│       ├── eval_judge.md         ← LLM-as-judge prompt for scoring
│       ├── meta_system.md        ← System prompt for the meta agent (planned)
│       ├── meta_design.md        ← "Design a new curation skill" prompt (planned)
│       └── meta_reflect.md       ← Self-reflection prompt for novelty (planned)
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

The core ADAS algorithm. Runs overnight via cron.

**Configuration:**
- Iterations per night: 5 (start conservative, increase as you gain confidence)
- Meta agent model: Nemotron 3 Super via Ollama (you have DGX Spark)
- Max self-reflection rounds: 2 (per the paper)
- Max debug retries on error: 3

**Loop pseudocode:**

```
load archive from archive/index.json

for i in range(iterations_per_night):

    # Step 1: Design
    prompt = build_design_prompt(archive)
    new_skill = meta_agent.generate(prompt)
    # Returns: { thought, name, skill_md }

    # Step 2: Self-reflect for novelty (2 rounds)
    for round in [1, 2]:
        reflection = meta_agent.reflect(new_skill, archive)
        new_skill = reflection.revised_skill

    # Step 3: Validate
    write new_skill.md to temp directory
    try:
        scores = evaluator.score(new_skill, test_set)
    except Error as e:
        # Debug loop (up to 3 retries)
        new_skill = meta_agent.debug(new_skill, error=e)
        scores = evaluator.score(new_skill, test_set)

    # Step 4: Archive
    save to archive/skill_{id}/
    update archive/index.json with scores

    # Step 5: Deploy winner (if new best)
    if scores.total > archive.best_score:
        copy SKILL.md → skills/youtube-curator/SKILL.md
        log "New best skill deployed: {name} (score: {total})"
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

**Morning delivery (current cron stub uses 4:00 AM local time):**

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
    "date": "2026-04-29",
    "picks": [
      {"video_id": "xxx", "reaction": "up", "skill_version": "skill_012"},
      {"video_id": "yyy", "reaction": "down", "skill_version": "skill_012"},
      {"video_id": "zzz", "reaction": null, "skill_version": "skill_012"}
    ]
  }
  ```
- The evaluation harness uses this feedback for the "alignment" scoring dimension
- Over time, the meta agent learns patterns: you prefer tactical/practical over thought-leadership, short over long, etc.

---

### Component 6: Cron schedule

Two cron jobs in NemoClaw:

```json
{
  "jobs": [
    {
      "name": "adas-evolution",
      "schedule": "0 2 * * *",
      "command": "python3 ~/.openclaw/workspace/adas/meta_agent.py",
      "description": "Run ADAS loop at 2 AM — 5 iterations"
    },
    {
      "name": "morning-digest",
      "schedule": "0 4 * * *",
      "command": "openclaw agent --agent main --local -m '/youtube-curator'",
      "description": "Send top 3 videos to Telegram at 4 AM"
    }
  ]
}
```

---

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
- [ ] Score all 3 baselines against the cached video set
- [ ] Verify scores are sensible (baselines should score differently)
- [ ] Build the feedback ingestion from Telegram reactions

### Phase 3: Meta agent loop (day 5-7)
- [ ] Write meta agent prompts (design, reflect, debug)
- [ ] Build `meta_agent.py` with the full loop
- [ ] Run 5 iterations manually, inspect generated skills
- [ ] Verify archive grows correctly with scores and metadata
- [ ] Test auto-deployment of winning skill

### Phase 4: Automation and feedback (day 8-10)
- [ ] Configure cron jobs in NemoClaw (2 AM evolution, 7 AM delivery)
- [ ] Set up Telegram reaction capture for feedback loop
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
