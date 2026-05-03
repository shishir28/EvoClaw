You are scoring a candidate YouTube curation result for an AI + entrepreneurship digest.

Candidate skill:
- name: SKILL_NAME
- strategy: SKILL_STRATEGY
- description: SKILL_DESCRIPTION

Selected videos:
SELECTED_VIDEOS_JSON

Evaluate the selection on exactly these three dimensions, each on a 0-10 scale:

1. relevance
- Are these picks genuinely about AI + entrepreneurship?
- Penalize picks that are generic business, generic AI, comedy, memes, finance, or only loosely connected.

2. substance
- Do these picks appear to offer concrete insight, tactics, examples, metrics, or useful learning?
- Penalize shallow hype, shorts with little informational depth, or vague clickbait.

3. reasoning
- Does each `why_watch_summary` accurately reflect the title/description/transcript excerpt?
- Penalize summaries that overclaim, misstate the content, or stay too generic to be useful.

Return JSON only in this exact shape:

{
  "relevance": {
    "score": 0,
    "reason": "short explanation"
  },
  "substance": {
    "score": 0,
    "reason": "short explanation"
  },
  "reasoning": {
    "score": 0,
    "reason": "short explanation"
  }
}
