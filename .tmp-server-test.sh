#!/usr/bin/env bash
# Throwaway harness #2: does the systemd path work on a real host, without touching the
# soapbot.service already there?
set -u

cd /opt/soapbot-test
git fetch --quiet origin master
git checkout --quiet master
git reset --quiet --hard origin/master
echo "bootstrap revision: $(git rev-parse --short HEAD)"

/opt/soapbot-test/.venv/bin/python scripts/bootstrap.py \
  --dir /opt/soapbot-test --port 6186 --autostart --unit soapbot-test 2>&1 | tail -25

echo "=== systemctl ==="
systemctl is-active soapbot-test
systemctl --no-pager show soapbot-test -p ActiveState -p SubState -p FragmentPath
echo "=== health ==="
curl -s http://127.0.0.1:6186/api/health
echo
echo "=== the pre-existing unit is untouched ==="
ls -l /etc/systemd/system/soapbot.service | awk '{print $5, $9}'
grep -c "Managed by soapbot bootstrap" /etc/systemd/system/soapbot.service
