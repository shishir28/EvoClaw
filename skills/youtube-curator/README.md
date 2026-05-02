# YouTube curator skill

This directory is meant to hold the **production OpenClaw skill** used for the daily digest.

## Current state

`SKILL.md` exists and acts as the current production placeholder. Right now it reflects a hand-written **recency-style baseline** rather than a skill that has been discovered and promoted by the ADAS loop.

Today this path is mainly useful as:

- the canonical future deployment target for the best archived skill
- a concrete example of the `SKILL.md` shape the evaluator is built around
- a placeholder production skill while archive promotion does not exist yet

## Intended role

Once the full system is implemented, this file will be updated automatically whenever a newly evaluated skill outperforms the current best archived skill.

Expected workflow:

1. `adas/meta_agent.py` generates a candidate skill.
2. `adas/evaluator.py` scores it on cached video sets.
3. The result is stored in `adas/archive/skill_xxx/`.
4. If it becomes the new best performer, its `SKILL.md` is copied here.
5. The scheduled delivery job runs this production skill.

Current limitation: only the placeholder file exists today; generation, archive promotion, and scheduled delivery are all still future steps.

## Output contract

The production skill is expected to produce a Telegram-friendly digest with:

- 3 selected videos
- title, channel, duration, and age
- a direct "why watch" summary for each pick
- a closing feedback prompt for 👍 / 👎 reactions
