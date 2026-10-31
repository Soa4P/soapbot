#!/usr/bin/env bash
# Verify login -> QR -> login-state against the real container, printing shapes we can code to.
set -u
TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/napcat-probe/webui.json'))['token'])")
HASH=$(python3 -c "import hashlib,sys;print(hashlib.sha256((sys.argv[1]+'.napcat').encode()).hexdigest())" "$TOKEN")

CRED=$(curl -s -X POST http://127.0.0.1:60999/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"hash\":\"$HASH\"}" \
  | python3 -c 'import json,sys
d = json.load(sys.stdin)
data = d.get("data") or {}
print(data.get("Credential", "") if isinstance(data, dict) else "")')
echo "credential length: ${#CRED}"

echo "--- QR ---"
curl -s -X POST http://127.0.0.1:60999/api/QQLogin/GetQQLoginQrcode \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $CRED" -d '{"qrcode":true}' \
  > /tmp/qr.json
python3 - <<'PY'
import json
payload = json.load(open("/tmp/qr.json"))
print("code:", payload.get("code"), "message:", payload.get("message"))
data = payload.get("data")
if isinstance(data, dict):
    print("keys:", list(data))
    image = str(data.get("qrcode") or data.get("image") or "")
    print("image length:", len(image), "prefix:", image[:30])
else:
    print("data type:", type(data).__name__, str(data)[:120])
PY

echo "--- login status ---"
curl -s -X POST http://127.0.0.1:60999/api/QQLogin/CheckLoginStatus \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $CRED" -d '{}' | head -c 300
echo
