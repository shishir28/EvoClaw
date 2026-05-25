# Cron configuration

`cron/jobs.json` is the canonical schedule source for EvoClaw jobs. `cron/runner.py` is the executor that validates env vars, runs a named job, and writes per-run logs under `cron/logs/`.

Scheduling itself lives outside EvoClaw in NemoClaw/OpenShell. This folder keeps the job catalog and runner logic only.

## Files

| File | Purpose |
|---|---|
| `jobs.json` | Canonical job definitions: name, schedule, module, args, required env |
| `runner.py` | CLI that reads `jobs.json`, validates config, runs a named job, and logs output |
| `logs/` | Per-run log files written by `runner.py` |

## Jobs

The jobs in `jobs.json` are configured for daily runs in the `Australia/Sydney` timezone:

| Job | Schedule | What it does |
|---|---|---|
| `refresh-video-cache` | 12:30 AM AEST | Refreshes the reusable YouTube candidate cache |
| `adas-evolution` | 1:30 AM AEST | Runs 3 meta-agent cycles: generate -> reflect -> evaluate -> archive -> promote |
| `morning-digest` | 4:30 AM AEST | Runs the production skill, formats top 3 picks, sends Telegram messages |
| `reaction-capture` | 8:30 AM AEST | Polls Telegram for reactions and writes feedback entries |
| `daily-status` | 9:00 AM AEST | Writes a compact daily status summary |

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
