#!/usr/bin/env bash
# Install EvoClaw cron jobs into the current user's crontab.
#
# Usage:
#   bash cron/install.sh           # preview, then confirm before writing
#   bash cron/install.sh --force   # write without prompting

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
RUNNER="$PROJECT_ROOT/cron/runner.py"
FORCE="${1:-}"

# ---------------------------------------------------------------------------
# Build the crontab entries from cron/jobs.json
# ---------------------------------------------------------------------------
# Each entry:
#   - Changes into the project root so relative paths in jobs.json resolve
#   - Calls runner.py which handles env loading, validation, logging

mapfile -t EVOCLAW_ENTRIES < <("$VENV_PYTHON" "$RUNNER" --print-crontab)

echo "The following entries will be added to your crontab (Australia/Sydney timezone):"
echo ""
printf '  %s\n' "${EVOCLAW_ENTRIES[@]}"
echo ""

# ---------------------------------------------------------------------------
# Check for duplicates before writing
# ---------------------------------------------------------------------------
existing_crontab="$(crontab -l 2>/dev/null || true)"

already_installed=0
for entry in "${EVOCLAW_ENTRIES[@]}"; do
    job_name="$(sed -E 's/.*--job ([^ ]+).*/\1/' <<< "$entry")"
    if echo "$existing_crontab" | grep -q -- "--job $job_name"; then
        echo "WARNING: a $job_name entry already exists in your crontab."
        already_installed=1
    fi
done

if [ "$already_installed" -eq 1 ]; then
    echo ""
    echo "Remove the existing EvoClaw entries from your crontab before re-running this script."
    exit 1
fi

# ---------------------------------------------------------------------------
# Confirm and write
# ---------------------------------------------------------------------------
if [ "$FORCE" != "--force" ]; then
    read -r -p "Install these entries? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

mkdir -p "$PROJECT_ROOT/cron/logs"

(
    echo "$existing_crontab"
    echo ""
    echo "# EvoClaw automated jobs (installed by cron/install.sh; generated from cron/jobs.json)"
    printf '%s\n' "${EVOCLAW_ENTRIES[@]}"
) | crontab -

echo "Done. Current crontab:"
crontab -l
