# Cron configuration

This directory contains the planned scheduler configuration for EvoClaw automation.

## `jobs.json`

`jobs.json` defines two intended recurring jobs:

1. `adas-evolution`  
   Runs the overnight ADAS loop that should generate, evaluate, and archive new candidate skills.

2. `morning-digest`  
   Runs the production YouTube curator skill to send the daily Telegram digest.

## Important current limitation

The schedule file is present, but the underlying automation is not fully wired yet:

- `adas/meta_agent.py` does not exist yet
- Telegram delivery and feedback capture are not implemented yet
- the scheduled workflow should be treated as a design stub, not a production-ready scheduler

## Relationship to the plan

The timing and responsibilities in `jobs.json` come from `Plan.md`, which describes:

- overnight evolution for skill discovery
- morning execution for user-facing delivery
- future feedback capture for improving alignment
