---
name: llm-substance-judge
version: "1.0"
strategy: llm-substance-judge
description: Fetch 20 candidates, score each for actionable substance using local Nemotron, pick top 3.
author: human-baseline
score: null
---

# Skill: LLM Substance-Judge YouTube Curator

## Goal
Find the 3 videos with the highest ratio of actionable insight to hype — particularly hidden gems from smaller channels that velocity-based methods miss. Uses local Nemotron inference to judge substance.

## Steps

### 1. Fetch a broad candidate pool
Search YouTube for videos published in the last **7 days** using these queries:
- "AI startup lessons"
- "building AI product"
- "AI entrepreneur advice"
- "machine learning founder story"
- "artificial intelligence business"

Collect up to 5 results per query. Deduplicate by video ID. Target ~20 unique candidates.

### 2. Filter for English language
Discard any video where the title or description appears to be written in a non-English language. Check for non-Latin scripts (e.g. Telugu, Vietnamese, Arabic, Chinese, Hindi) or where the majority of words are clearly not English. When in doubt, keep the video.

### 3. Enrich with transcripts (best-effort)
For each candidate, attempt to fetch the auto-generated English transcript via `youtube-transcript-api`. If unavailable, fall back to using the video description only.

### 4. Score each candidate with Nemotron
Send each candidate to local Nemotron (via Ollama)/vLLM with the following prompt:

---
**System:** You are a curator for a daily AI + entrepreneurship digest. Score this YouTube video on its practical value to a technical founder or entrepreneur.

**User:**
Title: {title}
Channel: {channel}
Description: {description}
Transcript excerpt (first 1500 chars): {transcript_or_description}

Rate this video on a scale of 1–10 for SUBSTANCE using these criteria:
- 10: Specific tactics, metrics, or decisions; real case study data; things you can act on today
- 7-9: Clear frameworks or insights with concrete examples
- 4-6: General advice that's somewhat useful but not specific
- 1-3: Clickbait, vague hype, or no actionable content

Respond with JSON only: {"score": <int>, "reason": "<one sentence>"}
---

Collect the score and one-sentence reason for each candidate.

### 5. Sort and select
Sort candidates by `substance_score` descending.
Pick the top 3.

### 6. Generate summaries
For each of the 3 picks, write the "why watch" summary using the Nemotron-generated reason as a starting point. Make it direct and specific — name the insight, not just the topic.

### 7. Format the Telegram message
Return the result in this exact format:

```
🎬 Your AI + startup picks for today

1. "{title}"
   @{channel} · {duration_min} min · {age}
   🔗 {url}
   → {why_watch_summary}

2. ...

3. ...

React 👍 or 👎 to each to help me improve picks.
```

## Notes
- This skill is slower than the others (one LLM call per candidate). Run it with adequate time before the delivery window.
- If Nemotron returns invalid JSON, retry once; if it fails again, skip the candidate.
- Prefer videos with available transcripts — a missing transcript is a soft quality penalty since the scoring will be less accurate.
