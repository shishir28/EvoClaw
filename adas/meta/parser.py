"""Parses meta-agent LLM responses into validated Candidate objects.

Handles fence stripping, JSON extraction, field validation, and YAML
frontmatter validation so that callers never touch raw LLM text.
"""

from __future__ import annotations

import json
import re

from adas.meta.models import Candidate

# The meta-agent response is split into two parts: a small JSON head carrying the
# structured fields (thought/name, plus verdict/issues/checks for reflection) and a
# separate fenced ```markdown block carrying the full SKILL.md document. Keeping the
# multi-line SKILL.md out of the JSON string avoids the unescaped-quote failures and
# the grammar-constrained run-on that small local models produce when a whole document
# is embedded inside a single JSON string field.
REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"name", "version", "strategy", "description", "author", "score"}
)
SUPPORTED_STRATEGIES: frozenset[str] = frozenset(
    {"recency", "engagement-velocity", "llm-substance-judge"}
)
REQUIRED_BODY_HEADERS: frozenset[str] = frozenset({"## Goal", "## Steps"})
SKILL_BODY_MIN_LENGTH: int = 200
# Patterns that indicate an LLM tried to escape its sandboxed role and inject
# instructions into other prompts or system contexts.
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "system prompt",
    "you are now",
    "act as",
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
    """Parse and return the JSON head object found in *text*.

    Only the small structured head is JSON; the SKILL.md body is delivered in a
    separate fenced block (see :func:`extract_skill_md_block`)."""
    return _extract_json_object(text)


def extract_skill_md_block(text: str) -> str:
    """Return the SKILL.md document carried after the JSON head in *text*.

    The document is delivered in a fenced markdown block that, per contract, begins
    with YAML frontmatter ('---'). We anchor on that first frontmatter line rather
    than on code-fence markers, because models vary the fence width (``` vs ````)
    and the skill body itself frequently contains nested ``` code fences (e.g. an
    output-format template). Trailing closing-fence/blank lines are stripped."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "---"), None)
    if start is None:
        raise ValueError(
            "Response did not contain a SKILL.md document (no '---' frontmatter)."
        )
    body = lines[start:]
    # Drop the model's trailing closing fence (``` / ````) and any blank lines.
    while body and (not body[-1].strip() or set(body[-1].strip()) == {"`"}):
        body.pop()
    return "\n".join(body)


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


def parse_candidate_response(text: str) -> Candidate:
    """Parse a generator response (JSON head + fenced SKILL.md) into a Candidate."""
    head = parse_response(text)
    skill_md = extract_skill_md_block(text)
    for key in ("thought", "name"):
        if key not in head:
            raise ValueError(f"Response missing required field: '{key}'")
        if not isinstance(head[key], str):
            raise ValueError(
                f"Field '{key}' must be a string, got {type(head[key]).__name__}."
            )
    return Candidate(thought=head["thought"], name=head["name"], skill_md=skill_md)


def parse_reflection_response(text: str) -> dict:
    """Parse a reflector response: JSON head plus an optional fenced SKILL.md block.

    Returns the head dict with ``skill_md`` added when a fenced block is present.
    On an accept-without-repair (no fenced block) ``skill_md`` is omitted so the
    caller falls back to the original candidate's document."""
    head = parse_response(text)
    try:
        head["skill_md"] = extract_skill_md_block(text)
    except ValueError:
        pass
    return head


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


def _extract_body(skill_md: str) -> str:
    """Return the text after the closing frontmatter delimiter."""
    lines = skill_md.split("\n")
    close_idx: int | None = None
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                close_idx = i
                break
    if close_idx is None:
        return skill_md
    return "\n".join(lines[close_idx + 1:])


def validate_skill_body(skill_md: str) -> None:
    """Raise ValueError when the SKILL.md body fails structural or safety checks."""
    body = _extract_body(skill_md)

    if len(body.strip()) < SKILL_BODY_MIN_LENGTH:
        raise ValueError(
            f"SKILL.md body is too short ({len(body.strip())} chars). "
            f"Minimum required: {SKILL_BODY_MIN_LENGTH}."
        )

    missing_headers = [h for h in sorted(REQUIRED_BODY_HEADERS) if h not in body]
    if missing_headers:
        raise ValueError(
            "SKILL.md body is missing required headers: "
            + ", ".join(f"'{h}'" for h in missing_headers)
        )

    lower_body = body.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lower_body:
            raise ValueError(
                f"SKILL.md body contains a potential prompt injection pattern: {pattern!r}"
            )


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
    validate_skill_body(candidate.skill_md)
    if frontmatter.get("name") != candidate.name:
        raise ValueError(
            "Candidate name must match frontmatter 'name': "
            f"{candidate.name!r} != {frontmatter.get('name')!r}"
        )
    return frontmatter
