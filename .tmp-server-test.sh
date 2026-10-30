#!/usr/bin/env bash
# Throwaway harness: test the one-click install on a real Ubuntu host.
# Pinned to a commit because raw.githubusercontent serves cached copies of "master".
set -u

rm -rf /opt/soapbot-test
curl -fsSL "https://raw.githubusercontent.com/Soa4P/soapbot/4d102da/deploy/install.sh" \
  -o /tmp/soapbot-install.sh
echo "wait_for_apt present: $(grep -c wait_for_apt /tmp/soapbot-install.sh)"

DIR=/opt/soapbot-test bash /tmp/soapbot-install.sh --port 6186 --no-service 2>&1 | tail -45
echo "=== exit=${PIPESTATUS[0]} ==="
