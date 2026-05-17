"""
EvoClaw job runner.

Reads cron/jobs.json, validates required env vars, runs a named job via the
project's venv Python, and logs output to cron/logs/.

Usage:
    python cron/runner.py --list
    python cron/runner.py --job morning-digest
    python cron/runner.py --job morning-digest --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root is one level up from this file.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = PROJECT_ROOT / "cron" / "jobs.json"
LOGS_DIR = PROJECT_ROOT / "cron" / "logs"
ENV_FILE = PROJECT_ROOT / ".env"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def _load_env() -> None:
    """Load .env into the current process environment."""
    if not ENV_FILE.exists():
        return
    with ENV_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _load_jobs() -> list[dict]:
    if not JOBS_FILE.exists():
        print(f"ERROR: jobs file not found: {JOBS_FILE}", file=sys.stderr)
        sys.exit(1)
    return json.loads(JOBS_FILE.read_text())["jobs"]


def _find_job(jobs: list[dict], name: str) -> dict:
    for job in jobs:
        if job["name"] == name:
            return job
    names = [j["name"] for j in jobs]
    print(f"ERROR: unknown job '{name}'. Available: {', '.join(names)}", file=sys.stderr)
    sys.exit(1)


def _check_required_env(job: dict) -> list[str]:
    """Return list of missing required env vars for this job."""
    missing = []
    for key in job.get("required_env", []):
        value = os.environ.get(key, "").strip()
        if not value:
            missing.append(key)
    return missing


def _expand_args(args: list, project_root: Path) -> list[str]:
    """Expand {PROJECT_ROOT} placeholders and resolve relative paths to absolute."""
    result = []
    for arg in args:
        expanded = str(arg).replace("{PROJECT_ROOT}", str(project_root))
        # If it looks like a relative file path (contains / or .) and not a flag, resolve it.
        if not expanded.startswith("-") and ("/" in expanded or expanded.endswith(".json")):
            candidate = project_root / expanded
            if candidate.exists() or expanded.startswith("{"):
                expanded = str(candidate.resolve())
        result.append(expanded)
    return result


def _run_job(job: dict, dry_run: bool = False) -> int:
    name = job["name"]
    module = job["module"]
    args = _expand_args(job.get("args", []), PROJECT_ROOT)

    cmd = [str(VENV_PYTHON), "-m", module] + args
    cmd_str = " ".join(cmd)

    if dry_run:
        print(f"[dry-run] would run: {cmd_str}")
        return 0

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_file = LOGS_DIR / f"{name}-{timestamp}.log"

    print(f"Running job '{name}'...")
    print(f"  command : {cmd_str}")
    print(f"  log     : {log_file}")

    with log_file.open("w") as lf:
        header = (
            f"# EvoClaw job: {name}\n"
            f"# started: {timestamp}\n"
            f"# command: {cmd_str}\n\n"
        )
        lf.write(header)
        lf.flush()

        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lf.write(result.stdout or "")
        lf.write(f"\n# exit code: {result.returncode}\n")

    if result.returncode == 0:
        print(f"  status  : OK (exit 0)")
        # Print last few lines of output for quick confirmation.
        lines = (result.stdout or "").strip().splitlines()
        for line in lines[-10:]:
            print(f"  | {line}")
    else:
        print(f"  status  : FAILED (exit {result.returncode})")
        lines = (result.stdout or "").strip().splitlines()
        for line in lines[-20:]:
            print(f"  | {line}")

    return result.returncode


def _list_jobs(jobs: list[dict]) -> None:
    print(f"{'NAME':<20} {'SCHEDULE':<15} DESCRIPTION")
    print("-" * 70)
    for job in jobs:
        print(f"{job['name']:<20} {job['schedule']:<15} {job.get('description', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="EvoClaw job runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job", metavar="NAME", help="Run a named job")
    group.add_argument("--list", action="store_true", help="List available jobs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without executing",
    )
    args = parser.parse_args()

    _load_env()
    jobs = _load_jobs()

    if args.list:
        _list_jobs(jobs)
        return

    job = _find_job(jobs, args.job)

    missing = _check_required_env(job)
    if missing:
        print(
            f"ERROR: job '{job['name']}' requires the following env vars to be set "
            f"(check your .env file): {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)

    exit_code = _run_job(job, dry_run=args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
