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
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Project root is one level up from this file.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = PROJECT_ROOT / "cron" / "jobs.json"
LOGS_DIR = PROJECT_ROOT / "cron" / "logs"
ENV_FILE = PROJECT_ROOT / ".env"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def _python_executable() -> str:
    """Return the Python executable used to run jobs.

    Native installs use the project virtualenv. Containerized installs usually
    bind-mount the repository into /app without a .venv, so they should use the
    image's Python instead.
    """
    configured = os.environ.get("EVOCLAW_PYTHON", "").strip()
    if configured:
        return configured
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


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



def _build_cron_entries(
    jobs: list[dict],
    project_root: Path = PROJECT_ROOT,
    python_executable: str | None = None,
    logs_dir: Path = LOGS_DIR,
    env_file: Path | None = None,
    user: str | None = None,
) -> list[str]:
    """Build crontab lines from jobs.json so schedules have one source of truth."""
    python_cmd = python_executable or _python_executable()
    runner_path = project_root / "cron" / "runner.py"
    entries: list[str] = []
    for job in jobs:
        name = str(job["name"])
        schedule = str(job["schedule"])
        log_file = logs_dir / f"cron-{name}.log"
        command_parts = []
        if env_file is not None:
            command_parts.append(f"source {shlex.quote(str(env_file))}")
        command_parts.append(f"cd {shlex.quote(str(project_root))}")
        command_parts.append(
            f"{shlex.quote(python_cmd)} {shlex.quote(str(runner_path))} --job {shlex.quote(name)}"
        )
        command = " && ".join(command_parts)
        line = (
            f"{schedule} "
            f"{(user + ' ') if user else ''}"
            f"bash -lc {shlex.quote(command)} "
            f">> {shlex.quote(str(log_file))} 2>&1"
        )
        entries.append(line)
    return entries


def _models_endpoint(base_url: str) -> str:
    """Return the OpenAI-compatible /models endpoint for a configured base URL."""
    trimmed = base_url.strip().rstrip("/")
    if not trimmed:
        raise ValueError("LLM_BASE_URL must not be empty.")
    return f"{trimmed}/models"


def _check_openai_compatible_health(
    base_url: str,
    model: str,
    timeout_seconds: float = 5.0,
) -> tuple[bool, str]:
    """Validate that an OpenAI-compatible backend is reachable and exposes the model."""
    try:
        endpoint = _models_endpoint(base_url)
    except ValueError as exc:
        return False, str(exc)

    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"LLM backend is not reachable at {endpoint}: {exc}"

    models = payload.get("data", []) if isinstance(payload, dict) else []
    model_ids = {
        str(item.get("id"))
        for item in models
        if isinstance(item, dict) and item.get("id") is not None
    }
    if model and model_ids and model not in model_ids:
        return False, (
            f"LLM model '{model}' was not found at {endpoint}. "
            f"Available models: {', '.join(sorted(model_ids))}"
        )
    return True, f"LLM backend reachable at {endpoint}."


def _run_healthchecks(job: dict) -> list[str]:
    """Run optional job-specific preflight checks and return failure messages."""
    healthcheck = str(job.get("healthcheck", "")).strip()
    if not healthcheck:
        return []
    if healthcheck != "openai-compatible":
        return [f"Unknown healthcheck '{healthcheck}' for job '{job.get('name', '')}'."]

    ok, message = _check_openai_compatible_health(
        base_url=os.environ.get("LLM_BASE_URL", ""),
        model=os.environ.get("LLM_MODEL", ""),
    )
    return [] if ok else [message]

def _run_job(job: dict, dry_run: bool = False) -> int:
    name = job["name"]
    module = job["module"]
    args = _expand_args(job.get("args", []), PROJECT_ROOT)

    cmd = [_python_executable(), "-m", module] + args
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
    group.add_argument(
        "--print-crontab",
        action="store_true",
        help="Print crontab entries generated from jobs.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without executing",
    )
    parser.add_argument(
        "--cron-user",
        help="User field to include for system cron files such as /etc/cron.d",
    )
    parser.add_argument(
        "--cron-env-file",
        help="Optional env file to source before each generated cron command",
    )
    args = parser.parse_args()

    _load_env()
    jobs = _load_jobs()

    if args.list:
        _list_jobs(jobs)
        return

    if args.print_crontab:
        env_file = Path(args.cron_env_file) if args.cron_env_file else None
        for entry in _build_cron_entries(
            jobs,
            env_file=env_file,
            user=args.cron_user,
        ):
            print(entry)
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

    healthcheck_failures = _run_healthchecks(job)
    if healthcheck_failures:
        print(
            f"ERROR: job '{job['name']}' failed preflight healthcheck(s):",
            file=sys.stderr,
        )
        for failure in healthcheck_failures:
            print(f"- {failure}", file=sys.stderr)
        sys.exit(3)

    exit_code = _run_job(job, dry_run=args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
