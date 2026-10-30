#!/bin/sh
# Snapshot the soapbot data volume.
#
# A backup nobody runs is not a backup. This script is what the systemd timer calls, and
# it deliberately ends by *listing* the archive: a file that exists but cannot be opened
# is the failure mode that silently passes every check based on size or exit code.
#
# Installed layout (see deploy/soapbot-backup.{service,timer}):
#   /opt/soapbot/deploy/backup.sh   <- this file, from the repository checkout
#   /etc/systemd/system/soapbot-backup.{service,timer}
set -eu

BACKUP_DIR="${BACKUP_DIR:-/opt/soapbot/backups}"
KEEP="${KEEP:-3}"
COMPOSE="${COMPOSE:-docker compose -f /opt/soapbot/deploy/docker-compose.yml}"

mkdir -p "$BACKUP_DIR"

# Ask the running container which volume is actually mounted at /data, rather than
# assuming the compose project name -- a renamed directory changes it.
VOLUME=$($COMPOSE ps -q soapbot 2>/dev/null | head -1 | xargs -r docker inspect -f \
    '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true)
if [ -z "${VOLUME}" ]; then
    VOLUME="${SOAPBOT_VOLUME:-deploy_soapbot-data}"
fi

STAMP=$(date +%F-%H%M%S)
ARCHIVE="$BACKUP_DIR/soapbot-$STAMP.tgz"

# --network none: the archive step needs no network, and a backup that can reach out is
# one more thing that can be made to fail.
docker run --rm --network none \
    -v "$VOLUME":/data:ro \
    -v "$BACKUP_DIR":/backup \
    alpine:3 \
    tar czf "/backup/soapbot-$STAMP.tgz" -C /data .

# Keep the newest $KEEP, drop the rest.
ls -1t "$BACKUP_DIR"/soapbot-*.tgz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

# Prove it opens. Failing here means the backup is worthless, and it is better to know
# now than during a restore.
if ! tar -tzf "$ARCHIVE" >/dev/null 2>&1; then
    echo "backup archive is not readable: $ARCHIVE" >&2
    exit 1
fi

echo "$ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
