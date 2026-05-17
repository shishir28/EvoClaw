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
# Build the crontab entries
# ---------------------------------------------------------------------------
# Each entry:
#   - Changes into the project root so relative paths in jobs.json resolve
#   - Calls runner.py which handles env loading, validation, logging

EVOLUTION_ENTRY="0 2 * * * cd $PROJECT_ROOT && $VENV_PYTHON $RUNNER --job adas-evolution >> $PROJECT_ROOT/cron/logs/cron-adas-evolution.log 2>&1"
DIGEST_ENTRY="0 7 * * * cd $PROJECT_ROOT && $VENV_PYTHON $RUNNER --job morning-digest >> $PROJECT_ROOT/cron/logs/cron-morning-digest.log 2>&1"
REACTION_ENTRY="30 9 * * * cd $PROJECT_ROOT && $VENV_PYTHON $RUNNER --job reaction-capture >> $PROJECT_ROOT/cron/logs/cron-reaction-capture.log 2>&1"

echo "The following entries will be added to your crontab (Australia/Sydney timezone):"
echo ""
echo "  $EVOLUTION_ENTRY"
echo "  $DIGEST_ENTRY"
echo "  $REACTION_ENTRY"
echo ""

# ---------------------------------------------------------------------------
# Check for duplicates before writing
# ---------------------------------------------------------------------------
existing_crontab="$(crontab -l 2>/dev/null || true)"

already_installed=0
if echo "$existing_crontab" | grep -q "adas-evolution"; then
    echo "WARNING: an adas-evolution entry already exists in your crontab."
    already_installed=1
fi
if echo "$existing_crontab" | grep -q "morning-digest"; then
    echo "WARNING: a morning-digest entry already exists in your crontab."
    already_installed=1
fi
if echo "$existing_crontab" | grep -q "reaction-capture"; then
    echo "WARNING: a reaction-capture entry already exists in your crontab."
    already_installed=1
fi

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
    echo "# EvoClaw automated jobs (installed by cron/install.sh)"
    echo "$EVOLUTION_ENTRY"
    echo "$DIGEST_ENTRY"
    echo "$REACTION_ENTRY"
) | crontab -

echo "Done. Current crontab:"
crontab -l
