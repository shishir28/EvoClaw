# YouTube curator skill

This directory holds the production `SKILL.md` used by the daily Telegram digest.

## Current role

- `SKILL.md` is the live production skill target.
- `deployment.json` records the deployed archive skill, score, timestamp, and previous deployment after promotion.
- `delivery_log.json` records each digest delivery, including selected video IDs and Telegram message IDs.
- `reaction_poll_offset.json` records the Telegram update offset after reaction capture runs.

## Workflow

1. `adas/meta_agent.py` generates and evaluates candidate skills.
2. Successful candidates are archived under `adas/archive/skill_*/`.
3. `adas/deployment/promoter.py` copies the archive winner here when it beats the current deployment record.
4. `adas.telegram_digest` reads this production skill and sends one Telegram message per selected video.
5. `adas.telegram_feedback` maps reactions on those messages back to individual videos and writes feedback.

## Output contract

The production skill should produce three video picks with title, channel, duration, age, URL, and a direct reason to watch. Delivery and feedback metadata is persisted beside this file.
