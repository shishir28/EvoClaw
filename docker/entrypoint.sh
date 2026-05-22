#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${EVOCLAW_APP_DIR:-/app}"
APP_USER="${EVOCLAW_APP_USER:-evoclaw}"
APP_UID="${EVOCLAW_UID:-1000}"
APP_GID="${EVOCLAW_GID:-1000}"
TZ="${TZ:-Australia/Sydney}"
CRON_FILE="/etc/cron.d/evoclaw"
ENV_FILE="/etc/evoclaw/env.sh"

ensure_user() {
    if ! getent group "$APP_GID" >/dev/null; then
        groupadd --gid "$APP_GID" "$APP_USER"
    fi

    if ! id -u "$APP_USER" >/dev/null 2>&1; then
        useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /bin/bash "$APP_USER"
    fi
}

write_cron_file() {
    mkdir -p "$APP_DIR/cron/logs"
    chown -R "$APP_UID:$APP_GID" "$APP_DIR/cron/logs"
    mkdir -p "$(dirname "$ENV_FILE")"

    printenv | while IFS='=' read -r name value; do
        if [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            printf 'export %s=%q\n' "$name" "$value"
        fi
    done > "$ENV_FILE"
    chown "$APP_UID:$APP_GID" "$ENV_FILE"
    chmod 0600 "$ENV_FILE"

    cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
TZ=$TZ
EVOCLAW_PYTHON=${EVOCLAW_PYTHON:-/usr/local/bin/python}

# EvoClaw automated jobs (container-managed)
30 0 * * * $APP_USER bash -lc 'source $ENV_FILE && cd $APP_DIR && /usr/local/bin/python cron/runner.py --job refresh-video-cache' >> $APP_DIR/cron/logs/cron-refresh-video-cache.log 2>&1
30 1 * * * $APP_USER bash -lc 'source $ENV_FILE && cd $APP_DIR && /usr/local/bin/python cron/runner.py --job adas-evolution' >> $APP_DIR/cron/logs/cron-adas-evolution.log 2>&1
30 4 * * * $APP_USER bash -lc 'source $ENV_FILE && cd $APP_DIR && /usr/local/bin/python cron/runner.py --job morning-digest' >> $APP_DIR/cron/logs/cron-morning-digest.log 2>&1
30 8 * * * $APP_USER bash -lc 'source $ENV_FILE && cd $APP_DIR && /usr/local/bin/python cron/runner.py --job reaction-capture' >> $APP_DIR/cron/logs/cron-reaction-capture.log 2>&1
EOF

    chmod 0644 "$CRON_FILE"
}

if [[ "${1:-}" == "cron" ]]; then
    ensure_user
    write_cron_file
    echo "EvoClaw cron scheduler starting with timezone: $TZ"
    echo "Project directory: $APP_DIR"
    echo "Generated files are written through the bind mount at $APP_DIR"
    exec cron -f
fi

ensure_user
exec gosu "$APP_USER" "$@"
