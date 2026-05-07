# YouTube curator skill

This directory is meant to hold the **production OpenClaw skill** used for the daily digest.

## Current state

`SKILL.md` exists as the current production skill target. It can now be updated by the Step 10 `SkillPromoter` when the archive winner beats the recorded production deployment.

Today this path is mainly useful as:

- the canonical deployment target for the best archived skill
- a concrete example of the `SKILL.md` shape the evaluator is built around
- the live file read by the current manual Step 11 digest runtime and the future scheduled daily digest

## Intended role

This file is updated by `adas/deployment/promoter.py` whenever a newly evaluated archive winner outperforms the current deployment record.

Expected workflow:

1. `adas/meta_agent.py` generates a candidate skill.
2. `adas/evaluator.py` scores it on cached video sets.
3. The result is stored in `adas/archive/skill_xxx/`.
4. If it becomes the new best performer, its `SKILL.md` is copied here.
5. `deployment.json` records the deployed skill ID, score, timestamp, and previous deployment.
6. The Step 11 digest runtime runs this production skill manually today, and the scheduled delivery job will reuse it later.

Current limitation: manual Telegram delivery now exists, but scheduled delivery and Telegram reaction capture are still future steps.

## Output contract

The production skill is expected to produce a Telegram-friendly digest with:

- 3 selected videos
- title, channel, duration, and age
- a direct "why watch" summary for each pick
- a closing feedback prompt for 👍 / 👎 reactions
- delivery metadata persisted in `delivery_log.json` beside this file
