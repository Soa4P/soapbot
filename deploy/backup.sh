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

# Why the archive is written into the volume and copied out through `docker exec cat`
# -----------------------------------------------------------------------------------
# `docker cp` cannot see a container's tmpfs mounts. The container's only writable tmpfs
# is /tmp, so a backup written there was invisible to `docker cp` — it failed with
# "Could not find the file /tmp/…" while `docker exec ls` listed the file in the same
# container (measured twice). Writing under /data (the volume) and streaming the bytes
# out with `docker exec cat` is immune to which mount type the target happens to be.
#
# Output is kept, not swallowed: when this fails the only useful thing an operator has
# is the reason. --keep 0 because retention is this script's job, on the host.
PENDING="/data/backups/pending-$STAMP"
compose exec -T soapbot python -m soapbot.cli backup create --out "$PENDING" --keep 0
# Resolve the one archive name without a shell glob: python prints the exact path.
# The directory arrives as argv, never interpolated into the code (a path is data).
ARCHIVE_IN=$(docker exec "$CID" python -c \
    'import glob, sys; hits = sorted(glob.glob(sys.argv[1] + "/*.zip")); print(hits[0] if hits else "")' \
    "$PENDING")
if [ -z "$ARCHIVE_IN" ]; then
    echo "the container wrote no archive; see the output above" >&2
    compose exec -T soapbot rm -rf "$PENDING" >/dev/null 2>&1 || true
    exit 1
fi
docker exec "$CID" cat "$ARCHIVE_IN" > "$ARCHIVE"
# The in-volume copy is transient: the volume must not grow with backups it holds twice.
compose exec -T soapbot rm -rf "$PENDING" >/dev/null 2>&1 || true
if [ ! -s "$ARCHIVE" ]; then
    echo "copying the archive out produced an empty file" >&2
    rm -f "$ARCHIVE"
    exit 1
fi

# The archive contains data/secret.key and .env: it is a credential, not just data.
chmod 600 "$ARCHIVE"

# Keep the newest $KEEP, drop the rest. The .tgz pattern is only here so an install that
# has been running since the tar days does not accumulate them forever.
ls -1t "$BACKUP_DIR"/soapbot-*.zip "$BACKUP_DIR"/soapbot-*.tgz 2>/dev/null \
    | tail -n +$((KEEP + 1)) | xargs -r rm -f

# Prove it *is* a soapbot backup, not merely an openable zip (audit S-DEP-17).
# The old self-check was `zipfile.testzip()`: an archive of an empty or wrong volume
# passes it — every entry intact, nothing inside. What actually distinguishes a usable
# snapshot is content: a manifest whose checksums name the database, and a database that
# begins with the SQLite magic at a plausible size. An empty `data/` (volume mount
# pointing at nothing) fails here instead of producing a green timer every night.
# `--user root` is required, not a relaxation: the archive is 0600 and owned by root on
# the host (a credential — it carries secret.key), while the image's default user is
# uid 10001, so an unprivileged read gets "Permission denied" and the check would report
# a perfectly good archive as unreadable (measured).
if ! docker run --rm --network none --user 0:0 --entrypoint python \
    -v "$BACKUP_DIR":/backup:ro "$IMAGE" \
    -c 'import json, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
if z.testzip() is not None:
    sys.exit("corrupt member")
manifest = json.loads(z.read("manifest.json"))
checksums = manifest.get("checksums") or {}
if not isinstance(checksums, dict):
    sys.exit("manifest has no checksums")
name = "data/soapbot.db"
if name not in checksums:
    sys.exit("manifest does not cover the database; the volume may be empty")
info = z.getinfo(name)
if info.file_size < 4096:
    sys.exit(f"database member is implausibly small ({info.file_size} bytes)")
if not z.open(name).read(16).startswith(b"SQLite format 3\x00"):
    sys.exit("database member is not SQLite")
' "/backup/$(basename "$ARCHIVE")"; then
    echo "backup archive is not a usable soapbot snapshot: $ARCHIVE" >&2
    exit 1
fi

echo "$ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
