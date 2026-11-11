#!/bin/sh
# Restore a backup produced by deploy/backup.sh into the data volume.
#
#   ./restore.sh /opt/soapbot/backups/soapbot-2026-11-10-120000.zip
#
# Two things this script will not do, both deliberate:
#
#   * It will not restore while the bot is running. SQLite has readers with an open
#     snapshot; replacing the file underneath them gives each connection a different
#     database, and the failure is corruption a week later rather than an error now.
#   * It will not write anything until the archive has been verified. scripts/restore.py
#     checks the manifest checksums, runs PRAGMA integrity_check on the staged copy and
#     only then renames the old database to soapbot.db.pre-restore-<stamp>. A failed
#     restore leaves the install exactly as it was.
#
# The restore runs as the image's own uid (10001), which owns the volume, so no step here
# needs root. It also runs with no network and read-only scripts.
set -eu

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
    echo "usage: $0 /path/to/soapbot-YYYY-MM-DD-HHMMSS.zip" >&2
    exit 2
fi

COMPOSE_FILE="${COMPOSE_FILE:-/opt/soapbot/deploy/docker-compose.yml}"
IMAGE="${IMAGE:-soapbot:hardened}"
ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

VOLUME=$(compose ps -q soapbot 2>/dev/null | head -1 | xargs -r docker inspect -f \
    '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true)
if [ -z "${VOLUME}" ]; then
    VOLUME="${SOAPBOT_VOLUME:-deploy_soapbot-data}"
fi

STOPPED=0
restart() {
    if [ "$STOPPED" = "1" ]; then
        compose start soapbot || echo "warning: could not restart soapbot" >&2
    fi
}
trap restart EXIT

echo "stopping soapbot (the database must not change during a restore)"
compose stop soapbot
STOPPED=1

ARCHIVE_DIR=$(cd "$(dirname "$ARCHIVE")" && pwd)
ARCHIVE_NAME=$(basename "$ARCHIVE")

# --data-dir is the volume: it carries both soapbot.db and config/, which is why the
# restore has one target instead of two that could disagree.
docker run --rm \
    --network none \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$VOLUME":/data \
    -v "$ROOT/scripts":/scripts:ro \
    -v "$ARCHIVE_DIR":/backup:ro \
    --entrypoint python \
    "$IMAGE" /scripts/restore.py "/backup/$ARCHIVE_NAME" \
        --data-dir /data --config-dir /data/config

# Only reached when the restore exited 0: a non-zero exit aborted the script above, the
# trap restarts the service, and nothing on the volume was replaced.
echo "starting soapbot"
compose start soapbot
STOPPED=0

echo "done. the previous database is at soapbot.db.pre-restore-* inside the volume;"
echo "delete it once the panel shows the expected data:"
echo "  docker run --rm -v $VOLUME:/data alpine:3 sh -c 'rm -f /data/soapbot.db.pre-restore-*'"
