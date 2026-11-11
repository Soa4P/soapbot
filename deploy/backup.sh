#!/bin/sh
# Snapshot the soapbot data volume, in the one format the restore path reads.
#
# A backup nobody runs is not a backup. This script is what the systemd timer calls, and
# it deliberately ends by *opening* the archive: a file that exists but cannot be read is
# the failure mode that silently passes every check based on size or exit code.
#
# Why this no longer tars the volume
# ----------------------------------
# The previous version ran `tar czf` over the live volume. Two problems, and they compound:
#
#   * SQLite in WAL mode keeps committed pages in `soapbot.db-wal`. Tarring the files can
#     capture the database and its -wal at different instants, or skip the -wal entirely.
#     The result opens cleanly and is silently missing the newest messages — a backup
#     that passes `tar -tzf`.
#   * It produced a different format from `scripts/backup.py`, which is what
#     `scripts/restore.py` reads. So the timer and the documented restore procedure were
#     two procedures: an operator following the docs could not use the timer's output.
#
# Now the timer runs the same `backup.py`, inside the app image (the host may have no
# Python and no SQLite), against the same volume the service mounts. The SQLite backup
# API takes a consistent snapshot while the bot keeps writing.
#
# Installed layout (see deploy/soapbot-backup.{service,timer}):
#   /opt/soapbot/deploy/backup.sh   <- this file, from the repository checkout
#   /etc/systemd/system/soapbot-backup.{service,timer}
set -eu

BACKUP_DIR="${BACKUP_DIR:-/opt/soapbot/backups}"
KEEP="${KEEP:-3}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/soapbot/deploy/docker-compose.yml}"
IMAGE="${IMAGE:-soapbot:hardened}"
ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# A function, not a command string. Expanding an unquoted $COMPOSE relied on
# word-splitting to turn one variable into four arguments, which breaks on a path
# with a space. Only the file path is configurable now.
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Ask the running container which volume is actually mounted at /data, rather than
# assuming the compose project name -- a renamed directory changes it.
VOLUME=$(compose ps -q soapbot 2>/dev/null | head -1 | xargs -r docker inspect -f \
    '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true)
if [ -z "${VOLUME}" ]; then
    VOLUME="${SOAPBOT_VOLUME:-deploy_soapbot-data}"
fi

STAMP=$(date +%F-%H%M%S)
ARCHIVE="$BACKUP_DIR/soapbot-$STAMP.zip"

# Why a helper container instead of `compose exec`: the image ships the installed wheel
# and no repository, so backup.py is not on its filesystem. Why `docker create` + `cp`
# instead of a bind mount for the output: /backup would be root-owned on the host and
# the container runs as uid 10001; writing inside the container and copying out avoids
# either loosening that directory or running the backup as root.
CID=$(docker create \
    --network none \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$VOLUME":/data:ro \
    -v "$ROOT/scripts":/scripts:ro \
    --entrypoint python \
    "$IMAGE" /scripts/backup.py \
        --data-dir /data --config-dir /data/config --out "/tmp/soapbot-$STAMP.zip")
# Cleanup must survive a failure halfway: an abandoned container holds a reference to the
# volume, and `docker volume rm` then refuses until someone notices.
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

docker start -a "$CID"
docker cp "$CID:/tmp/soapbot-$STAMP.zip" "$ARCHIVE"

# The archive contains data/secret.key and .env: it is a credential, not just data.
chmod 600 "$ARCHIVE"

# Keep the newest $KEEP, drop the rest. The .tgz pattern is only here so an install that
# has been running since the tar days does not accumulate them forever.
ls -1t "$BACKUP_DIR"/soapbot-*.zip "$BACKUP_DIR"/soapbot-*.tgz 2>/dev/null \
    | tail -n +$((KEEP + 1)) | xargs -r rm -f

# Prove it opens, with the same interpreter that wrote it.
if ! docker run --rm --network none --entrypoint python \
    -v "$BACKUP_DIR":/backup:ro "$IMAGE" \
    -c 'import sys, zipfile; z = zipfile.ZipFile(sys.argv[1]); sys.exit(1 if z.testzip() else 0)' \
    "/backup/$(basename "$ARCHIVE")"; then
    echo "backup archive is not readable: $ARCHIVE" >&2
    exit 1
fi

echo "$ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
