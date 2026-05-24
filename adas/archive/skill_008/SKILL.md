---
name: recency-first-tactical-enhanced
version: "1.0"
strategy: recency
description: Fetch the most recent and relevant videos on AI + entrepreneurship with transcripts, focusing on tactical founder content.
author: adas-meta
score: null
---

# Skill: Recency-First Tactical Enhanced YouTube Curator

## Goal
Surface the 3 most recently published videos about AI and entrepreneurship, with a focus on tactical founder content. Good for catching actionable insights and strategies for entrepreneurs.

## Steps

### 1. Fetch candidate videos
Search YouTube for videos published in the last **72 hours** using these queries:
- "AI startup tactics"
- "founder's guide to AI"
- "AI-driven business strategies"
- "entrepreneurship with AI"
- "scaling AI startups"

Collect up to 10 results per query. Deduplicate by video ID.

### 2. Filter for English language
Discard any video where the title or description appears to be written in a non-English language. Check for non-Latin scripts (e.g. Telugu, Vietnamese, Arabic, Chinese, Hindi) or where the majority of words are clearly not English. When in doubt, keep the video.

### 3. Filter for relevance
Discard any video where the title or description does NOT mention at least one of:
- AI, artificial intelligence, machine learning, LLM, GPT, agent, Claude, AGI or similar AI terms
- startup, founder, entrepreneur, SaaS, venture, funding

### 4. Filter for minimum quality
Discard videos from channels with fewer than **5,000 subscribers** (use channel subscriber count if available; skip this check if the data is missing).

### 5. Prefer transcript-rich videos
Prioritize videos that have transcripts available, as they are more likely to contain detailed and actionable content.

### 6. Sort and select
Sort the remaining candidates by `published_at` descending (newest first).
Pick the top 3.

### 7. Generate summaries
For each of the 3 picks, write a 1-2 sentence \"why watch\" summary that:
- Names the specific topic or insight covered
- Highlights how the content is actionable for founders

### 8. Format the Telegram message
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

Where:
- `{age}` = human-readable age ("2 hours ago", "1 day ago", etc.)
- `{duration_min}` = video duration rounded to nearest minute

## Fallback
If fewer than 3 videos pass all filters, expand the window to **14 days** and retry from Step 1.