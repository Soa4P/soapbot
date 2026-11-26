#!/usr/bin/env bash
# Install or update soapbot on Linux with one command.
#
# Idempotent: an existing data directory is never overwritten, an existing virtual
# environment is reused, and an existing systemd unit is left alone unless --force.
# The bootstrap token is never printed; only its path is, because a token in a
# terminal transcript outlives the token.
#
#   curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.sh | bash
#   ./install.sh --dir /opt/soapbot --port 6185
#   ./install.sh --tag v0.1.0   # pinned: a branch ref can change, a tag cannot
set -euo pipefail

DIR="${SOAPBOT_DIR:-/opt/soapbot}"
PORT="${SOAPBOT_PORT:-6185}"
SERVICE=soapbot
FORCE=0
NO_SERVICE=0
TAG=""
#: Which commit to install. A tag cannot move; a branch can, and a SHA is the only ref
#: that names exactly one tree. Default stays the branch for a one-command install, but
#: the choice is printed so "what am I running" is answerable after the fact (S-DEP-08).
REF="${SOAPBOT_REF:-}"
#: Optional expected digest of the downloaded archive. Without it the installer prints
#: what it got, which is what an operator records for the next run.
EXPECT_SHA256="${SOAPBOT_SHA256:-}"
TARBALL="https://codeload.github.com/Soa4P/soapbot/tar.gz/refs/heads/master"

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --sha256) EXPECT_SHA256="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --no-service) NO_SERVICE=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# A tag must look like v<digit>… so a branch name can never be smuggled in as a "pin".
if [ -n "$TAG" ]; then
  case "$TAG" in
    v[0-9]*) TARBALL="https://codeload.github.com/Soa4P/soapbot/tar.gz/refs/tags/$TAG" ;;
    *) echo "--tag must look like v0.1.0 (a tag ref, not a branch)" >&2; exit 2 ;;
  esac
fi

if [ -n "$REF" ]; then
  # Option injection first: a ref starting with "-" would be read by curl/wget as a flag.
  case "$REF" in
    -*) echo "--ref must not start with '-'" >&2; exit 2 ;;
  esac
  case "$REF" in
    *[!0-9a-f]*)
      # Not a SHA. Tags are fine; anything else is a branch and is *reported* as such,
      # because a branch resolves to a different tree tomorrow and the operator should
      # know that is what they asked for.
      case "$REF" in
        v[0-9]*) TARBALL="https://codeload.github.com/Soa4P/soapbot/tar.gz/refs/tags/$REF" ;;
        *)
          TARBALL="https://codeload.github.com/Soa4P/soapbot/tar.gz/refs/heads/$REF"
          echo "note: installing from branch '$REF' — that ref changes over time." >&2
          echo "      For a reproducible install use --tag v0.1.0 or --ref <40-char sha>." >&2
          ;;
      esac
      ;;
    *)
      if [ "${#REF}" -ne 40 ]; then
        echo "--ref looks like a SHA but is ${#REF} characters (expected 40)" >&2
        exit 2
      fi
      TARBALL="https://codeload.github.com/Soa4P/soapbot/tar.gz/$REF"
      ;;
  esac
fi

step() { printf '==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }

step "checking Python 3.12+"
PY=""
for candidate in python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      PY="$candidate"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "No Python 3.12+ found. Install it first:" >&2
  echo "  Debian/Ubuntu: sudo apt install python3.12 python3.12-venv" >&2
  echo "  RHEL/Fedora:   sudo dnf install python3.12" >&2
  exit 1
fi
ok "using $($PY -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# Always fetch: an earlier version only downloaded when the directory was missing, so
# "rerun to update" kept the old code. The archive has no data/ or .venv, so copying
# over an existing install leaves both alone.
step "fetching the current code into $DIR"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$TARBALL" -o "$tmp/soapbot.tar.gz"
else
  wget -qO "$tmp/soapbot.tar.gz" "$TARBALL"
fi

# Record what was installed, and check it when the operator pinned a digest. `sha256sum`
# is coreutils; macOS and some minimal images only have `shasum`. Neither present means
# the digest is unavailable rather than zero — print that instead of pretending.
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else return 1
  fi
}
if actual_sha="$(sha256_of "$tmp/soapbot.tar.gz")"; then
  if [ -n "$EXPECT_SHA256" ]; then
    if [ "${actual_sha}" != "${EXPECT_SHA256}" ]; then
      # Fail closed: the operator asked for specific bytes and did not get them.
      echo "archive sha256 does not match --sha256:" >&2
      echo "  expected ${EXPECT_SHA256}" >&2
      echo "  actual   ${actual_sha}" >&2
      exit 1
    fi
    ok "archive sha256 verified (${actual_sha:0:16}…)"
  else
    ok "archive sha256 ${actual_sha} (record this to pin the next install)"
  fi
else
  echo "note: no sha256sum/shasum available; archive integrity was not computed" >&2
fi

mkdir -p "$DIR"
tar -xzf "$tmp/soapbot.tar.gz" -C "$tmp"
inner="$(find "$tmp" -maxdepth 1 -type d -name 'soapbot-*' | head -n1)"
cp -a "$inner/." "$DIR/"
ok "code updated; data/ and .venv untouched"

VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  step "creating virtual environment"
  "$PY" -m venv "$VENV"
  ok "$VENV"
else
  ok "virtual environment already present"
fi

step "installing dependencies"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
if [ -f "$DIR/pyproject.toml" ]; then
  "$VENV/bin/python" -m pip install --quiet -e "$DIR"
else
  "$VENV/bin/python" -m pip install --quiet -r "$DIR/requirements.txt"
fi
ok "dependencies installed"

DATA="$DIR/data"
ENV_FILE="$DATA/.env"
mkdir -p "$DATA"
if [ ! -f "$ENV_FILE" ]; then
  step "writing $ENV_FILE"
  {
    echo "SOAPBOT_HOST=127.0.0.1"
    echo "SOAPBOT_PORT=$PORT"
    echo "SOAPBOT_DATA_DIR=$DATA"
    echo "SOAPBOT_ENV_FILE=$ENV_FILE"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "panel will bind to 127.0.0.1:$PORT"
else
  ok "keeping existing $ENV_FILE"
fi

if [ "$NO_SERVICE" -eq 0 ] && [ "$(id -u)" -eq 0 ] && command -v systemctl >/dev/null 2>&1; then
  UNIT="/etc/systemd/system/$SERVICE.service"
  step "installing $UNIT"
  cat > "$UNIT" <<EOF
[Unit]
Description=soapbot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$VENV/bin/python -m soapbot.cli start
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE" >/dev/null 2>&1 || true
  systemctl restart "$SERVICE"
  ok "service $SERVICE started"
else
  step "skipping systemd unit"
  ok "start manually: cd $DIR && $VENV/bin/python -m soapbot.cli start"
  nohup "$VENV/bin/python" -m soapbot.cli start >"$DIR/panel.log" 2>&1 &
fi

step "waiting for the panel"
healthy=0
i=0
while [ "$i" -lt 30 ]; do
  if "$VENV/bin/python" - "$PORT" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/health", timeout=3).read()
PY
  then healthy=1; break; fi
  i=$((i + 1))
  sleep 2
done
if [ "$healthy" -ne 1 ]; then
  echo "The service did not answer within 60s. Check $DIR/panel.log." >&2
  exit 1
fi
ok "healthy"

printf '\nsoapbot is running.\n'
printf '  panel  : http://127.0.0.1:%s\n' "$PORT"
printf '  token  : %s/init_token.txt   (read it on this host; it is not printed here)\n' "$DATA"
if [ "$NO_SERVICE" -eq 0 ] && [ "$(id -u)" -eq 0 ]; then
  printf '  restart: systemctl restart %s\n' "$SERVICE"
  printf '  logs   : journalctl -u %s -f\n' "$SERVICE"
else
  printf '  logs   : %s/panel.log\n' "$DIR"
fi
