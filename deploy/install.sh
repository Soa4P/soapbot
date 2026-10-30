#!/usr/bin/env bash
#
# One command from nothing to a running panel on Ubuntu/Debian — no Docker.
#
# Why this exists: the project shipped a docker-compose file and a set of careful
# documents, and still every deployment was a small project of its own. Docker Hub is
# unreachable from plenty of networks (the image build fails on step one), containers
# add a layer between the operator and their data directory, and none of it answers the
# only question a person actually has on a fresh VPS: "what do I type?".
#
# So this script is answer-shaped. It installs from source into one directory, writes one
# systemd unit, waits for /api/health to say ok, and prints exactly how to reach the
# panel. Everything it does is idempotent, so running it twice upgrades rather than
# duplicating — the second run of a setup script is where most of them do damage.
#
#   curl -fsSL .../install.sh | sudo bash        # fresh machine
#   sudo /opt/soapbot/deploy/install.sh          # upgrade in place
#
# Deliberately not done here: creating the QQ/protocol side or fetching an API key. Those
# need credentials this script cannot have, and silently guessing them is worse than
# stopping and saying so.

set -euo pipefail

REPO="${REPO:-https://github.com/Soa4P/soapbot.git}"
BRANCH="${BRANCH:-master}"
DIR="${DIR:-/opt/soapbot}"
HOST="${SOAPBOT_HOST:-127.0.0.1}"
PORT="${SOAPBOT_PORT:-6185}"
SERVICE=1
SKIP_APT=0

# Options are parsed by hand rather than with getopts because every flag here has a
# sensible default and the failure mode we care about — a mistyped flag — should print the
# usage, not silently install into the wrong directory.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-service) SERVICE=0; shift ;;
    --skip-apt) SKIP_APT=1; shift ;;
    -h|--help)
      sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown option: $1 (try --help)" >&2
      exit 2
      ;;
  esac
done

VENV="$DIR/.venv"
PYTHON="$VENV/bin/python"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

maybe_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

[[ $SKIP_APT -eq 1 ]] || command -v sudo >/dev/null 2>&1 || die "sudo not found: install with --skip-apt once you have root"

# ------------------------------------------------------------------ 1. prerequisites
say "[1/6] system packages"

if [[ $SKIP_APT -eq 0 ]]; then
  export DEBIAN_FRONTEND=noninteractive
  maybe_sudo apt-get update -qq
  maybe_sudo apt-get install -y -qq python3 python3-venv python3-pip git curl ca-certificates

  # Ubuntu 22.04 ships Python 3.10, which this project does not support (3.12 syntax and
  # typing behaviour). Rather than failing later with an unreadable traceback from pip,
  # the correct interpreter is installed here — but only when the distro one is too old.
  if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
  then
    say "[1/6] python 3.10 detected — adding the deadsnakes build for 3.12"
    maybe_sudo apt-get install -y -qq software-properties-common
    maybe_sudo add-apt-repository -y ppa:deadsnakes/ppa
    maybe_sudo apt-get update -qq
    maybe_sudo apt-get install -y -qq python3.12 python3.12-venv
  fi
fi

# Pick the newest supported interpreter; on 22.04 that is the deadsnakes one.
SYSTEM_PYTHON="$(command -v python3.12 || command -v python3)"

# ------------------------------------------------------------------------ 2. source
say "[2/6] source in $DIR"

if [[ -d "$DIR/.git" ]]; then
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" checkout --quiet "$BRANCH"
  # 'origin/<branch>' rather than HEAD: pinning to the remote keeps an operator's local
  # experiments in their checkout from silently becoming the deployed version.
  git -C "$DIR" reset --quiet --hard "origin/$BRANCH"
else
  maybe_sudo mkdir -p "$DIR"
  [[ "$(id -u)" -eq 0 ]] || sudo chown -R "$(id -u):$(id -g)" "$DIR"
  git clone --quiet --branch "$BRANCH" "$REPO" "$DIR"
fi

cd "$DIR"

# -------------------------------------------------------------------- 3. virtualenv
say "[3/6] python environment"

[[ -x "$PYTHON" ]] || "$SYSTEM_PYTHON" -m venv "$VENV"
"$PYTHON" -m pip install --quiet --upgrade pip

# -e because the panel shows git-tracked configuration and wants updatedb/update flows to
# be a `git pull` away; an editable install also keeps `soapbot` on PATH pointing at the
# code the service actually runs.
"$PYTHON" -m pip install --quiet -e .

# --------------------------------------------------------------------------- 4. UI
say "[4/6] web panel assets"

# The built assets are committed, so a normal clone already has them and this step is a
# no-op. It only fires when someone deliberately builds from a clean checkout — and when
# it cannot, it says so in one sentence instead of leaving a blank panel to debug.
if [[ ! -f "$DIR/src/soapbot/webui/dist/index.html" ]]; then
  if command -v npm >/dev/null 2>&1; then
    (cd "$DIR/webui" && npm install --no-audit --no-fund && npm run build)
  else
    die "no built panel found and npm is missing: install Node.js 20+ and re-run this script"
  fi
fi

# ----------------------------------------------------------------------- 5. config
say "[5/6] configuration"

if [[ ! -f "$DIR/.env" && -f "$DIR/.env.example" ]]; then
  cp "$DIR/.env.example" "$DIR/.env"
fi

# Absolute paths win over the template's relative ./data: the service runs from systemd
# with a different working directory, and a relative "data" there would silently create a
# second database next to the unit file.
DATA_DIR="$DIR/data"
CONFIG_DIR="$DIR/config"
mkdir -p "$DATA_DIR" "$CONFIG_DIR"

python_ensure_env() {
  "$PYTHON" - "$DIR/.env" "$@" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
wanted = dict(kv.split("=", 1) for kv in sys.argv[2:])
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out, seen = [], set()
for line in lines:
    key = line.split("=", 1)[0].strip()
    if key in wanted:
        out.append(f"{key}={wanted[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in wanted.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

python_ensure_env \
  "SOAPBOT_HOST=$HOST" \
  "SOAPBOT_PORT=$PORT" \
  "SOAPBOT_DATA_DIR=$DATA_DIR" \
  "SOAPBOT_CONFIG_DIR=$CONFIG_DIR" \
  "SOAPBOT_ENV_FILE=$DIR/.env"

"$PYTHON" -m soapbot.cli doctor >/dev/null 2>&1 || true

# ----------------------------------------------------------------------- 6. service
if [[ $SERVICE -eq 1 ]]; then
  say "[6/6] systemd service"

  UNIT="/etc/systemd/system/soapbot.service"
  RUN_AS="$(id -un)"
  RUN_GROUP="$(id -gn)"

  cat <<UNIT | maybe_sudo tee "$UNIT" >/dev/null
[Unit]
Description=soapbot panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$DIR/.env
ExecStart=$PYTHON -m soapbot.cli start
Restart=always
RestartSec=5
User=$RUN_AS
Group=$RUN_GROUP

[Install]
WantedBy=multi-user.target
UNIT

  maybe_sudo systemctl daemon-reload
  maybe_sudo systemctl enable --now soapbot

  # A faster restart loop than RestartSec alone: the unit restarts anyway, but waiting
  # here turns "is it up yet?" into an answer instead of a question.
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then break; fi
    sleep 1
  done

  maybe_sudo systemctl --no-pager --full status soapbot || {
    echo "--- last lines of the journal ---"
    maybe_sudo journalctl -u soapbot -n 30 --no-pager || true
    die "the service did not come up; the journal above is the reason"
  }
else
  say "[6/6] --no-service requested: start it with '$PYTHON -m soapbot.cli start'"
fi

say "done"
cat <<NEXT

  panel:  http://$HOST:$PORT   (loopback only — reachable on the host via SSH tunnel:
          ssh -L $PORT:127.0.0.1:$PORT <user>@<this-host>)
  token:  sudo -u $(id -un) $PYTHON -m soapbot.cli token
  config: $CONFIG_DIR   data: $DATA_DIR   env: $DIR/.env
  logs:   journalctl -u soapbot -f

  Next: open "Configure" (page 07), add a Provider (base_url + key), then add a QQ
  adapter and use the Test button next to each row. Both rows now show what to paste
  into NapCat, so nothing here requires guessing an address.

NEXT
