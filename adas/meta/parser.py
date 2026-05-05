"""Parses meta-agent LLM responses into validated Candidate objects.

Handles fence stripping, JSON extraction, field validation, and YAML
frontmatter validation so that callers never touch raw LLM text.
"""

from __future__ import annotations

import json
import re

try:
    from .models import Candidate
except ImportError:
    from meta.models import Candidate

REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"name", "version", "strategy", "description", "author", "score"}
)
SUPPORTED_STRATEGIES: frozenset[str] = frozenset(
    {"recency", "engagement-velocity", "llm-substance-judge"}
)

def strip_fences(text: str) -> str:
    """Remove ```json...``` or plain ``` fences from *text*."""
    text = re.sub(r"```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*", "", text)
    return text.strip()


def _extract_json_object(text: str) -> dict:
    # Try a full parse first; if that fails, scan for the first '{' so the
    # function tolerates LLM responses that wrap JSON in prose or preamble.
    cleaned = strip_fences(text)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(cleaned):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(cleaned[i:])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue

    raise ValueError("Response did not contain a valid JSON object.")


def parse_response(text: str) -> dict:
    """Parse and return the first JSON object found in *text*."""
    return _extract_json_object(text)


def extract_candidate(parsed: dict) -> Candidate:
    """Extract and validate a Candidate from a parsed response dict."""
    for key in ("thought", "name", "skill_md"):
        if key not in parsed:
            raise ValueError(f"Response missing required field: '{key}'")
        if not isinstance(parsed[key], str):
            raise ValueError(f"Field '{key}' must be a string, got {type(parsed[key]).__name__}.")
    return Candidate(
        thought=parsed["thought"],
        name=parsed["name"],
        skill_md=parsed["skill_md"],
    )


def parse_frontmatter(skill_md: str) -> dict[str, str | None]:
    """Parse YAML frontmatter between the opening and closing '---' delimiters."""
    lines = skill_md.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("skill_md does not start with YAML frontmatter ('---').")

    end: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        raise ValueError("YAML frontmatter is not closed with a second '---'.")

    fm: dict[str, str | None] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        fm[k] = None if v in ("null", "~", "") else v

    return fm


def validate_frontmatter(skill_md: str) -> dict[str, str | None]:
    """Parse frontmatter and raise ValueError for any contract violations."""
    fm = parse_frontmatter(skill_md)

    missing = REQUIRED_FRONTMATTER_KEYS - set(fm.keys())
    if missing:
        raise ValueError(f"Missing frontmatter keys: {', '.join(sorted(missing))}")

    if fm.get("author") != "adas-meta":
        raise ValueError(
            f"Frontmatter 'author' must be 'adas-meta', got: {fm.get('author')!r}"
        )

    if fm.get("score") is not None:
        raise ValueError(
            f"Frontmatter 'score' must be null, got: {fm.get('score')!r}"
        )

    strategy = fm.get("strategy")
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError(
            f"Unsupported strategy: {strategy!r}. "
            f"Must be one of: {sorted(SUPPORTED_STRATEGIES)}"
        )

    return fm


def validate_candidate(candidate: Candidate) -> dict[str, str | None]:
    """Validate candidate frontmatter and assert the name field matches."""
    frontmatter = validate_frontmatter(candidate.skill_md)
    if frontmatter.get("name") != candidate.name:
        raise ValueError(
            "Candidate name must match frontmatter 'name': "
            f"{candidate.name!r} != {frontmatter.get('name')!r}"
        )
    return frontmatter
