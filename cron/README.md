# Cron configuration

This directory contains the scheduler configuration and runtime tooling for EvoClaw automation.

## Files

| File | Purpose |
|---|---|
| `jobs.json` | Canonical job definitions — name, schedule, module, args, required env |
| `runner.py` | CLI that reads `jobs.json`, validates config, runs a named job, and logs output |
| `install.sh` | Installs the three crontab entries into the current user's crontab |
| `logs/` | Per-run log files written by `runner.py` and cron |

## Jobs

Three jobs run daily in the `Australia/Sydney` timezone:

| Job | Schedule | What it does |
|---|---|---|
| `adas-evolution` | 2:00 AM AEST | Runs 3 meta-agent cycles: generate → reflect → evaluate → archive → promote |
| `morning-digest` | 7:00 AM AEST | Runs the production skill, formats top 3 picks, sends Telegram digest |
| `reaction-capture` | 9:30 AM AEST | Polls Telegram for 👍/👎 reactions and writes feedback entries |

## Running a job manually

```bash
# List available jobs
python cron/runner.py --list

# Dry-run (print command without executing)
python cron/runner.py --job morning-digest --dry-run

# Real run
python cron/runner.py --job morning-digest
python cron/runner.py --job reaction-capture
python cron/runner.py --job adas-evolution
```

Logs are written to `cron/logs/<job-name>-<timestamp>.log`.

## Installing the crontab

```bash
bash cron/install.sh           # preview entries, then confirm
bash cron/install.sh --force   # install without prompting
```

To remove the entries later:
```bash
crontab -e   # delete the three EvoClaw lines manually
```

## Config validation

`runner.py` validates required env vars before running each job and exits with code 2
if any are missing, printing which keys are absent. This catches misconfiguration
before a scheduled job silently fails at midnight.

Required env vars per job:

- `adas-evolution` — none (uses cached video data and local LLM settings from `.env`)
- `morning-digest` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `reaction-capture` — `TELEGRAM_BOT_TOKEN`

## Daily schedule flow

```
02:00  adas-evolution   — overnight skill evolution (LLM-heavy, runs while you sleep)
07:00  morning-digest   — sends the curated digest to Telegram
09:30  reaction-capture — captures your 👍/👎 reactions from the morning digest
```

Reactions captured at 9:30 AM feed into the alignment scorer for the next night's
evolution cycle, closing the human-feedback loop.

## Relationship to the plan

The timing and responsibilities come from `Plan.md`:

- overnight evolution for skill discovery and promotion
- morning execution for user-facing delivery
- mid-morning reaction capture to close the feedback loop
