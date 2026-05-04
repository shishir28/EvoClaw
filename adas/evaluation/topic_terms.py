"""
Shared topic-term extraction helpers for evaluator scoring and feedback snapshots.
"""

from __future__ import annotations

import re

_GENERIC_TOPIC_TERMS = {
    "about",
    "advice",
    "agent",
    "agents",
    "artificial",
    "best",
    "business",
    "company",
    "content",
    "entrepreneur",
    "entrepreneurship",
    "founder",
    "founders",
    "future",
    "gpt",
    "guide",
    "howto",
    "ideas",
    "insights",
    "intelligence",
    "launch",
    "latest",
    "learn",
    "learning",
    "llm",
    "machine",
    "money",
    "news",
    "podcast",
    "product",
    "products",
    "saas",
    "startup",
    "startups",
    "story",
    "strategy",
    "tech",
    "tips",
    "tools",
    "video",
    "watch",
}


def extract_topic_terms(
    title: str,
    description: str,
    query_matched: str,
    tags: list[str],
) -> set[str]:
    source = " ".join([title, description, query_matched, " ".join(tags)]).lower()
    tokens = re.findall(r"[a-z0-9]+", source)
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in _GENERIC_TOPIC_TERMS
    }
