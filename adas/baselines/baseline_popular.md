---
name: engagement-velocity
version: "1.0"
strategy: engagement-velocity
description: Pick the 3 videos gaining views the fastest (views per hour since publish) from the last 7 days.
author: human-baseline
score: null
---

# Skill: Engagement-Velocity YouTube Curator

## Goal
Surface the 3 videos that are gaining traction fastest right now. A high views-per-hour rate means the audience is voting with attention — the content is striking a nerve.

## Steps

### 1. Fetch candidate videos
Search YouTube for videos published in the last **7 days** using these queries:
- "AI startup 2025"
- "artificial intelligence founder"
- "AI tools for entrepreneurs"
- "machine learning startup"

Collect up to 10 results per query. Deduplicate by video ID.

### 2. Filter for English language
Discard any video where the title or description appears to be written in a non-English language. Check for non-Latin scripts (e.g. Telugu, Vietnamese, Arabic, Chinese, Hindi) or where the majority of words are clearly not English. When in doubt, keep the video.

### 3. Filter for topic relevance
Keep only videos whose title or description contains at least one of:
- AI, artificial intelligence, machine learning, LLM, agents, GPT
- AND at least one of: startup, founder, entrepreneur, SaaS, product, funding, business

### 3. Apply quality floor
Discard videos from channels with fewer than **10,000 subscribers**. This removes low-quality spam while still allowing mid-size creators to surface.

### 4. Compute engagement velocity
For each remaining candidate, compute:

```
views_per_hour = view_count / hours_since_publish
```

Use at least 1 hour as the denominator to avoid division edge cases for brand-new uploads.

### 5. Sort and select
Sort by `views_per_hour` descending.
Pick the top 3.

### 6. Generate summaries
For each of the 3 picks, write a 1-2 sentence "why watch" summary that explains:
- What makes this video relevant to an AI founder or entrepreneur
- Any specific claim, metric, or insight visible in the title/description

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

Where:
- `{age}` = human-readable age ("2 days ago", etc.)
- `{duration_min}` = video duration rounded to nearest minute

## Fallback
If fewer than 3 videos pass the quality floor filter, lower the subscriber threshold to **1,000** and retry.
