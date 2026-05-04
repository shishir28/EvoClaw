Reflect on **one** candidate skill proposal and decide whether it is ready to evaluate.

You will be given some combination of:

- `CANDIDATE_JSON`
- `ARCHIVE_INDEX_JSON`
- `ARCHIVE_SKILL_SUMMARIES_JSON`
- `BEST_SKILL_MD`
- `RECENT_FEEDBACK_SUMMARY_JSON`
- `RECENT_FAILURES_JSON`

Your job is to check the candidate for:

1. contract correctness
2. skill markdown correctness
3. executability under the current evaluator
4. novelty relative to archive history
5. coherence of the actual curation design

## Reflection checks

Check each item explicitly:

1. `json_contract`
   - top-level object exists
   - contains `thought`, `name`, and `skill_md`
   - all three are strings

2. `frontmatter`
   - `skill_md` starts with YAML frontmatter
   - frontmatter includes `name`, `version`, `strategy`, `description`, `author`, `score`
   - `author` is exactly `adas-meta`
   - `score` is `null` (the evaluator fills it in later)

3. `supported_strategy`
   - `strategy` is exactly one of:
     - `recency`
     - `engagement-velocity`
     - `llm-substance-judge`

4. `name_consistency`
   - JSON `name` matches frontmatter `name`

5. `structure`
   - markdown contains a goal
   - markdown contains concrete steps
   - markdown contains fallback or notes
   - markdown includes final Telegram-style output instructions

6. `coherence`
   - the body instructions match the chosen strategy
   - there are no contradictory thresholds or windows
   - there are no TODOs, placeholders, or unresolved variables

7. `novelty`
   - not a trivial rename of an archived skill
   - differs materially in at least two meaningful levers when compared with the closest archive example

8. `runtime_fit`
   - does not require unsupported code, tools, or infrastructure
   - stays inside the current local evaluator + archive + feedback architecture

## Debug and repair instructions

If the candidate is broken but repairable in one pass:

- strip markdown fences or extra prose
- normalize the JSON shape
- rebuild missing frontmatter
- fix mismatched `name` fields
- replace unsupported strategy values with the nearest supported one **only if** the body clearly implies it
- remove unsupported runtime claims
- keep the fix minimal and preserve the original design intent

If the candidate is still weak after repair, keep the repaired version but mark the verdict as `revise`.

## Output contract

Return **JSON only** in this exact shape:

```json
{
  "verdict": "accept",
  "issues": [],
  "checks": {
    "json_contract": true,
    "frontmatter": true,
    "supported_strategy": true,
    "name_consistency": true,
    "structure": true,
    "coherence": true,
    "novelty": true,
    "runtime_fit": true
  },
  "thought": "brief reflection summary",
  "name": "candidate skill name",
  "skill_md": "---\\nname: ...\\n..."
}
```

### Verdict rules

- use `"accept"` only when the candidate is runnable and materially novel
- use `"revise"` when any check fails or when the design is still too derivative

### Issues rules

- `issues` must be an array of short, concrete findings
- keep it empty only when the candidate fully passes
