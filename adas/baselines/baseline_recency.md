---
name: recency-first
version: "1.0"
strategy: recency
description: Fetch the most recent videos on AI + entrepreneurship and pick the 3 newest.
author: human-baseline
score: null
---

# Skill: Recency-First YouTube Curator

## Goal
Surface the 3 most recently published videos about AI and entrepreneurship. Good for catching breaking news, product launches, and announcements before they go viral.

## Steps

### 1. Fetch candidate videos
Search YouTube for videos published in the last **48 hours** using these queries:
- "AI startup news"
- "artificial intelligence product launch"
- "AI entrepreneurship"

Collect up to 10 results per query. Deduplicate by video ID.

### 2. Filter for English language
Discard any video where the title or description appears to be written in a non-English language. Check for non-Latin scripts (e.g. Telugu, Vietnamese, Arabic, Chinese, Hindi) or where the majority of words are clearly not English. When in doubt, keep the video.

### 3. Filter for relevance
Discard any video where the title or description does NOT mention at least one of:
- AI, artificial intelligence, machine learning, LLM, GPT, agent
- startup, founder, entrepreneur, SaaS, venture, funding

### 3. Filter for minimum quality
Discard videos from channels with fewer than **1,000 subscribers** (use channel subscriber count if available; skip this check if the data is missing).

### 4. Sort and select
Sort the remaining candidates by `published_at` descending (newest first).
Pick the top 3.

### 5. Generate summaries
For each of the 3 picks, write a 1-2 sentence "why watch" summary that:
- Names the specific topic or insight covered
- Does NOT just paraphrase the title

### 6. Format the Telegram message
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
If fewer than 3 videos pass all filters, expand the window to **7 days** and retry from Step 1.
