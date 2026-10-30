#!/usr/bin/env bash
#
# Thin Linux entry point for a machine with nothing on it:
#
#   curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/install.sh | sudo bash
#
# Everything after "python is available" lives in scripts/bootstrap.py, which is the same
# installer Windows runs. Keeping two full implementations is how the first version of this
# file drifted: it only spoke systemd, so every improvement had to be written twice and the
# Windows copy never existed at all. This wrapper exists only to obtain Python and hand off.

set -euo pipefail

REPO="${REPO:-https://github.com/Soa4P/soapbot.git}"
BRANCH="${BRANCH:-master}"
DIR="${DIR:-/opt/soapbot}"
BOOTSTRAP_ARGS=("$@")

maybe_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

die() {
  printf '\n%s\n' "$*" >&2
  exit 1
}

wait_for_apt() {
  # A fresh VPS very often has unattended-upgrades mid-run. Charging into it yields
  # "Could not get lock /var/lib/dpkg/lock-frontend", which turns a 30-second wait into a
  # failure that reads like this project's fault. Found on a real host: <1 min after boot.
  local waited=0
  while ! flock -n /var/lib/dpkg/lock-frontend true 2>/dev/null; do
    if [[ $waited -ge 180 ]]; then
      die "another apt process still holds the package lock; let it finish and re-run"
    fi
    [[ $waited -eq 0 ]] && printf '      waiting for the package lock'
    sleep 5
    waited=$((waited + 5))
    printf '.'
  done
  [[ $waited -gt 0 ]] && printf ' done\n'
  return 0
}

have_python() {
  command -v python3 >/dev/null 2>&1 || command -v python3.12 >/dev/null 2>&1
}

# "Python exists" and "Python can build a venv" are different claims, and Debian splits
# them: python3 ships without ensurepip, so `python3 -m venv` fails telling you to install
# python3-venv. Checking only that python3 exists is how the first test install died here,
# on a machine that plainly had Python 3.12.
usable_python() {
  have_python || return 1
  local candidate
  candidate="$(command -v python3.12 || command -v python3)"
  "$candidate" - >/dev/null 2>&1 <<'PY'
import sys

raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
  [[ $? -eq 0 ]] || return 1
  "$candidate" -c 'import ensurepip' >/dev/null 2>&1
}

if ! usable_python; then
  export DEBIAN_FRONTEND=noninteractive
  wait_for_apt
  maybe_sudo apt-get update -qq
  maybe_sudo apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates
fi

# Ubuntu 22.04's 3.10 cannot run this project. Installing it here beats letting pip fail
# seven steps later with a traceback nobody asked for.
if command -v python3 >/dev/null 2>&1 && ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
then
  maybe_sudo apt-get install -y -qq software-properties-common
  maybe_sudo add-apt-repository -y ppa:deadsnakes/ppa
  maybe_sudo apt-get update -qq
  maybe_sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip
fi

PYTHON="$(command -v python3.12 || command -v python3)"

if [[ -d "$DIR/scripts" ]]; then
  cd "$DIR"
elif [[ -d "$DIR/.git" ]]; then
  cd "$DIR"
else
  maybe_sudo mkdir -p "$DIR"
  [[ "$(id -u)" -eq 0 ]] || sudo chown -R "$(id -u):$(id -g)" "$DIR"
  # From here on the installer owns everything: venv, dependencies, UI assets, absolute
  # paths, and whichever supervisor this machine actually has.
  "$PYTHON" - "$REPO" "$BRANCH" "$DIR" <<'PY'
import subprocess
import sys

repo, branch, target = sys.argv[1:4]
if subprocess.run(["git", "clone", "--quiet", "--branch", branch, repo, target]).returncode:
    raise SystemExit(f"could not clone {repo}")
PY
  cd "$DIR"
fi

"$PYTHON" scripts/bootstrap.py --dir "$DIR" "${BOOTSTRAP_ARGS[@]}"
