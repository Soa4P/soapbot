#!/usr/bin/env bash
# Harness #7: the whole protocol-end flow, on a real host, through the panel's own API.
set -u
docker rm -f napcat-probe >/dev/null 2>&1
pkill -f "soapbot-e2e" 2>/dev/null

rm -rf /opt/soapbot-e2e
git clone --quiet --branch master https://github.com/Soa4P/soapbot.git /opt/soapbot-e2e
cd /opt/soapbot-e2e
echo "revision: $(git rev-parse --short HEAD)"

/usr/bin/python3 -m venv .venv
.venv/bin/python -m pip install --quiet -e . 2>&1 | tail -2
mkdir -p data

SOAPBOT_DATA_DIR=/opt/soapbot-e2e/data \
SOAPBOT_HOST=127.0.0.1 SOAPBOT_PORT=6189 SOAPBOT_ENABLE_RUNTIME=false \
nohup .venv/bin/python -m soapbot.cli start > /tmp/e2e-panel.log 2>&1 &
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:6189/api/health >/dev/null 2>&1 && break
  sleep 1
done
echo "health: $(curl -s http://127.0.0.1:6189/api/health)"

echo "=== status before start ==="
curl -s http://127.0.0.1:6189/api/protocol/napcat/status

echo
echo "=== start it ==="
curl -s -X POST http://127.0.0.1:6189/api/protocol/napcat/start

echo
echo "=== poll ==="
for i in $(seq 1 20); do
  S=$(curl -s http://127.0.0.1:6189/api/protocol/napcat/status)
  echo "$S" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status"), "starting=" + str(d.get("starting")), "docker=" + str(d.get("docker")), "logged_in=" + str(d.get("logged_in")))'
  echo "$S" | grep -q '"status": *"running"' && break
  sleep 3
done

echo "=== qr ==="
curl -s -o /tmp/qr-resp.json -w 'http=%{http_code}\n' http://127.0.0.1:6189/api/protocol/napcat/qr
python3 - <<'PY'
import json
try:
    payload = json.load(open("/tmp/qr-resp.json"))
except Exception:
    payload = {}
url = payload.get("url") or ""
print("ok:", payload.get("ok"), "url:", url[:60])
PY

echo "=== scan (the port should be found too) ==="
curl -s http://127.0.0.1:6189/api/protocol/scan | python3 -c 'import json,sys; d=json.load(sys.stdin); print([(r["port"], r["kind"]) for r in d["results"]])'
