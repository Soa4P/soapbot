#!/usr/bin/env bash
# Harness #4: upgrade an install that already has data (the one thing still untested).
# Deliberately NOT touching /opt/soapbot: that deployment runs in Docker and docker
# compose reads its .env, so rewriting DATA_DIR/HOST there would break the live bot.
set -u

echo "=== 0. clear the leftover test process ==="
pkill -f "/opt/soapbot-test/.venv" 2>/dev/null
sleep 1
ss -ltn 2>/dev/null | grep -E '6186' || echo "6186 free"

echo "=== 1. fresh install at the current commit ==="
rm -rf /opt/soapbot-upgrade
curl -fsSL "https://raw.githubusercontent.com/Soa4P/soapbot/e16096d/deploy/install.sh" \
  -o /tmp/si.sh
DIR=/opt/soapbot-upgrade bash /tmp/si.sh --port 6187 --no-service 2>&1 | tail -8

echo "=== 2. give it data a real install would have ==="
cd /opt/soapbot-upgrade
cat >> .env <<'ENV'
DEEPSEEK_API_KEY=sk-upgrade-test-key
ENV
# A provider the operator added through the panel, i.e. the thing that must survive.
cat > data/config/providers.yaml <<'YAML'
providers:
  - id: deepseek
    kind: openai_compat
    label: DeepSeek
    base_url: https://api.deepseek.com/v1
    api_key: env:DEEPSEEK_API_KEY
    model: deepseek-flash
    priority: 10
YAML
sqlite_rows() {
  ls -l data/*.db 2>/dev/null | wc -l
}
echo "providers written, db files: $(sqlite_rows)"

echo "=== 3. restart it so the data is real, then upgrade in place ==="
pkill -f "soapbot-upgrade" 2>/dev/null
sleep 1
/opt/soapbot-upgrade/.venv/bin/python scripts/bootstrap.py --dir /opt/soapbot-upgrade \
  --port 6187 --no-service 2>&1 | tail -12

echo "=== 4. did the upgrade keep anything dangerous? ==="
echo "--- .env keys (duplicates would mean a rewrite that appends) ---"
grep -c '^SOAPBOT_HOST=' .env
grep -c '^SOAPBOT_DATA_DIR=' .env
grep '^SOAPBOT_HOST=\|^SOAPBOT_PORT=\|^SOAPBOT_DATA_DIR=' .env
echo "--- provider survived? ---"
grep -c 'id: deepseek' data/config/providers.yaml
echo "--- health ---"
curl -s http://127.0.0.1:6187/api/health
echo
echo "=== 5. --check on the installed copy ==="
/opt/soapbot-upgrade/.venv/bin/python scripts/bootstrap.py --dir /opt/soapbot-upgrade \
  --port 6187 --check 2>&1 | tail -12
