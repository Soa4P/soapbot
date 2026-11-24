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
# Why this runs inside the service container
# ------------------------------------------
# It used to start a one-shot helper with the volume mounted ``:ro`` and call
# ``scripts/backup.py`` from the checkout. That helper failed on every run: SQLite in
# WAL mode needs to write its ``-shm`` sidecar to open a database, so against a
# read-only mount it answers "unable to open database file" — the backup could not read
# the database it exists to protect (measured on this deployment; the timer had been
# silently producing nothing). ``docker compose exec`` into the running service reuses
# the connection that already has the database open read-write; the archive is then
# copied out, so retention and ``chmod 600`` stay on the host where they are auditable.
#
# The implementation is the package's (``soapbot backup``), which is also what the CLI
# and the docs use — one code path, one format (audit S-DEP-12).
#
# Installed layout (see deploy/soapbot-backup.{service,timer}):
#   /opt/soapbot/deploy/backup.sh   <- this file, from the repository checkout
#   /etc/systemd/system/soapbot-backup.{service,timer}
set -eu

BACKUP_DIR="${BACKUP_DIR:-/opt/soapbot/backups}"
KEEP="${KEEP:-3}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/soapbot/deploy/docker-compose.yml}"
IMAGE="${IMAGE:-soapbot:hardened}"

# A function, not a command string. Expanding an unquoted $COMPOSE relied on
# word-splitting to turn one variable into four arguments, which breaks on a path
# with a space. Only the file path is configurable now.
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP=$(date +%F-%H%M%S)
ARCHIVE="$BACKUP_DIR/soapbot-$STAMP.zip"

# Why `compose exec` and not a helper container with the volume mounted `:ro`
# ---------------------------------------------------------------------------
# The helper version failed on every run, and the reason is worth stating: SQLite in
# WAL mode opens a database by writing to its `-shm` sidecar, so `mode=ro` against a
# read-only bind mount answers "unable to open database file" — the backup could not
# even read the database it was supposed to protect. Measured on this deployment.
#
# Running the CLI inside the *service* container removes the problem at the root: that
# container already has the database open read-write (it is the writer), the package is
# installed there, and no extra container or bind mount is involved. The backup still
# writes only its own output file; the archive is copied out to the host directory so
# retention and `chmod 600` stay here, where they are auditable.
CID=$(compose ps -q soapbot 2>/dev/null | head -1)
if [ -z "$CID" ]; then
    echo "soapbot container is not running; a live WAL database cannot be snapshotted safely" >&2
    exit 1
fi

# --keep 0: retention is this script's job, and it deletes outside the container.
compose exec -T soapbot python -m soapbot.cli backup create \
    --out "/tmp/soapbot-backup-$STAMP" --keep 0 >/dev/null
# One archive per directory, so the wildcard resolves to exactly one file.
docker cp "$CID:/tmp/soapbot-backup-$STAMP/*.zip" "$ARCHIVE"
# The in-container copy is transient: the volume must not grow with backups it never reads.
compose exec -T soapbot rm -rf "/tmp/soapbot-backup-$STAMP" >/dev/null 2>&1 || true

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
