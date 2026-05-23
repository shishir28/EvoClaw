#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_TAG="${IMAGE_TAG:-evoclaw-cron-test}"
TZ_VALUE="${TZ:-Australia/Sydney}"
APP_USER="${EVOCLAW_APP_USER:-evoclaw}"
CONTAINER_APP_DIR="${EVOCLAW_APP_DIR:-/app}"
CONTAINER_PYTHON="${EVOCLAW_PYTHON:-/usr/local/bin/python}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "ERROR: python3 is required to build the expected crontab locally." >&2
    exit 1
fi

EXPECTED_FILE="$(mktemp)"
ACTUAL_FILE="$(mktemp)"
trap 'rm -f "$EXPECTED_FILE" "$ACTUAL_FILE"' EXIT

cat > "$EXPECTED_FILE" <<CRON_HEADER
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
TZ=$TZ_VALUE
EVOCLAW_PYTHON=$CONTAINER_PYTHON

# EvoClaw automated jobs (container-managed; generated from cron/jobs.json)
CRON_HEADER

APP_USER="$APP_USER" CONTAINER_APP_DIR="$CONTAINER_APP_DIR" CONTAINER_PYTHON="$CONTAINER_PYTHON" "$PYTHON_BIN" - <<'PY' >> "$EXPECTED_FILE"
import os
from pathlib import Path
import sys

repo_root = Path.cwd()
sys.path.insert(0, str(repo_root / "cron"))
import runner  # noqa: E402

jobs = runner._load_jobs()
for entry in runner._build_cron_entries(
    jobs,
    project_root=Path(os.environ["CONTAINER_APP_DIR"]),
    python_executable=os.environ["CONTAINER_PYTHON"],
    logs_dir=Path(os.environ["CONTAINER_APP_DIR"]) / "cron" / "logs",
    env_file=Path("/etc/evoclaw/env.sh"),
    user=os.environ["APP_USER"],
):
    print(entry)
PY

docker build -t "$IMAGE_TAG" .
docker run --rm     -e TZ="$TZ_VALUE"     -e EVOCLAW_APP_USER="$APP_USER"     -e EVOCLAW_APP_DIR="$CONTAINER_APP_DIR"     -e EVOCLAW_PYTHON="$CONTAINER_PYTHON"     "$IMAGE_TAG" cron-print > "$ACTUAL_FILE"

if ! diff -u "$EXPECTED_FILE" "$ACTUAL_FILE"; then
    echo "ERROR: container-generated /etc/cron.d/evoclaw content did not match expectations." >&2
    exit 1
fi

echo "Docker cron generation matches cron/jobs.json."
