# Cron configuration

This directory contains the scheduler configuration and runtime tooling for EvoClaw automation.

## Files

| File | Purpose |
|---|---|
| `jobs.json` | Canonical job definitions — name, schedule, module, args, required env |
| `runner.py` | CLI that reads `jobs.json`, validates config, runs a named job, and logs output |
| `install.sh` | Installs crontab entries generated from `jobs.json` into the current user's crontab |
| `logs/` | Per-run log files written by `runner.py` and cron |

The preferred production path is the Docker scheduler in `docker-compose.yml`.
`install.sh` remains available for native/manual machines, but it is not needed
when the `evoclaw-cron` container is running.

## Jobs

The jobs in `jobs.json` run daily in the `Australia/Sydney` timezone:

| Job | Schedule | What it does |
|---|---|---|
| `refresh-video-cache` | 12:30 AM AEST | Refreshes the reusable YouTube candidate cache |
| `adas-evolution` | 1:30 AM AEST | Runs 3 meta-agent cycles: generate → reflect → evaluate → archive → promote |
| `morning-digest` | 4:30 AM AEST | Runs the production skill, formats top 3 picks, sends Telegram messages |
| `reaction-capture` | 8:30 AM AEST | Polls Telegram for 👍/👎 reactions and writes feedback entries |

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

Native host crontab install:

```bash
bash cron/install.sh           # preview entries, then confirm
bash cron/install.sh --force   # install without prompting
```

To remove the entries later:
```bash
crontab -e   # delete the EvoClaw lines manually
```

## Running cron inside Docker

```bash
docker compose up -d --build evoclaw
docker compose logs -f evoclaw
```

The container generates its cron file from `cron/jobs.json` and bind-mounts
the repository at `/app`, so generated files are written back into this working
tree:

- `cron/logs/*.log`
- `adas/archive/**`
- `adas/test_sets/feedback.json`
- `skills/youtube-curator/delivery_log.json`
- `skills/youtube-curator/reaction_poll_offset.json`
- `skills/youtube-curator/SKILL.md` and deployment metadata when promotion runs

For local vLLM on the host, Docker uses:

```text
LLM_BASE_URL=http://host.docker.internal:9000/v1
```

Override that without editing `.env` by setting:

```bash
EVOCLAW_LLM_BASE_URL=http://host.docker.internal:9000/v1 docker compose up -d --build evoclaw
```

## Config validation

`runner.py` validates required env vars before running each job and exits with code 2
if any are missing, printing which keys are absent. Jobs may also declare a
preflight healthcheck; `adas-evolution` checks the OpenAI-compatible `/models`
endpoint and exits with code 3 if the LLM backend is unreachable or the configured
model is not listed. This catches misconfiguration before a scheduled job fails
deep inside candidate generation.

Required env vars per job:

- `refresh-video-cache` — `YOUTUBE_API_KEY`
- `adas-evolution` — `LLM_BASE_URL`, `LLM_MODEL`; also checks the OpenAI-compatible `/models` endpoint before starting
- `morning-digest` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `reaction-capture` — `TELEGRAM_BOT_TOKEN`

## Daily schedule flow

```
00:30  refresh-video-cache — refreshes the YouTube candidate cache
01:30  adas-evolution      — overnight skill evolution (LLM-heavy, runs while you sleep)
04:30  morning-digest      — sends the curated picks to Telegram
08:30  reaction-capture    — captures your 👍/👎 reactions from the morning digest
```

Reactions captured at 8:30 AM feed into the alignment scorer for the next night's
evolution cycle, closing the human-feedback loop.

## Relationship to the plan

The timing and responsibilities come from `Plan.md`:

- overnight evolution for skill discovery and promotion
- morning execution for user-facing delivery
- mid-morning reaction capture to close the feedback loop
