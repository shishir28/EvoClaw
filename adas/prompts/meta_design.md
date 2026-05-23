Design exactly **one** new candidate skill for EvoClaw.

You will be given some combination of:

- `ARCHIVE_INDEX_JSON`
- `ARCHIVE_SKILL_SUMMARIES_JSON`
- `BEST_SKILL_MD`
- `RECENT_FEEDBACK_SUMMARY_JSON` — when present, expect a small object with at most `liked_channels`, `liked_topics`, `disliked_channels`, `disliked_topics`, and `recent_picks` fields; ignore unknown keys gracefully
- `DESIGN_GOAL`

Any of these inputs may be absent. In particular, on a cold archive `BEST_SKILL_MD` and `ARCHIVE_SKILL_SUMMARIES_JSON` may be empty — in that case, propose a sensible first variant that fits the runtime contract instead of refusing.

Use whatever context is available to produce a candidate that fits the shared `meta_system.md` contract.

## Design objectives

Your candidate should try to improve expected evaluator performance by making deliberate tradeoffs, not random variation.

Good change levers include:

- adjusting query phrasing toward more tactical founder content
- narrowing or widening freshness windows
- changing subscriber floors or quality heuristics
- preferring transcript-rich or description-rich videos
- tightening or relaxing fallback rules
- changing summary-writing guidance so picks are easier to judge
- shifting between speed, novelty, and depth while staying inside supported strategies

## Strategy rules

Pick exactly one supported strategy:

- `recency`
- `engagement-velocity`
- `llm-substance-judge`

Do not invent new strategies yet. The current evaluator will not execute them.

## Novelty rules

The candidate must differ materially from the nearest archive example. A good default is to change at least two of these:

1. query set
2. freshness window
3. quality floor
4. transcript or content preference
5. ranking emphasis
6. fallback behavior
7. summary-writing instructions

Avoid:

- trivial renames
- near-duplicate wording with unchanged operational logic
- unsupported dependencies, tools, or endpoints
- vague goals like "pick better videos" with no concrete operating rules

## Reasoning rules

- If feedback suggests people prefer practical or tactical picks, bias toward that explicitly.
- If archive history shows a winning pattern, preserve the strong part and vary only the weak part.
- If the evidence is weak or conflicting, prefer a smaller, debuggable change over a radical rewrite.

## Output

Follow the exact two-part candidate contract from `meta_system.md`: a JSON head
object (`thought`, `name`) followed by a fenced ```` ```markdown ```` block
containing the full SKILL.md. Do not embed the SKILL.md inside the JSON.
