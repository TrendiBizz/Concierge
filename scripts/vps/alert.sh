#!/bin/bash
# Deliver a failed health check to a mailbox that is actually read.
#
# Before this, `healthcheck.sh` exited non-zero and cron tried to mail root — but the VPS has no MTA
# at all (no sendmail, no msmtp), so every alert was discarded. The API could be in a restart loop
# and nothing left the machine. This sends over the external SMTP relay the product already uses,
# from the host, so it still works when the containers are down.
#
# Usage (cron):  healthcheck.sh || alert.sh   -- reads the check's JSON on stdin.
set -u
ENV_FILE=${ENV_FILE:-/opt/trendi/shared/api.env}
STAMP_FILE=${STAMP_FILE:-/opt/trendi/monitoring/.last_alert}
QUIET_SECONDS=${QUIET_SECONDS:-3600}   # at most one alert an hour, so an outage is not a flood

now=$(date +%s)
if [ -f "$STAMP_FILE" ]; then
  last=$(cat "$STAMP_FILE" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$QUIET_SECONDS" ]; then
    echo "alert suppressed (last sent $((now - last))s ago)" >&2
    exit 0
  fi
fi

payload=$(cat 2>/dev/null || true)
[ -z "$payload" ] && payload='{"status":"unknown","detail":"healthcheck produced no output"}'

python3 - "$ENV_FILE" "$payload" <<'PY'
import json, os, smtplib, ssl, sys
from email.message import EmailMessage

env_file, payload = sys.argv[1], sys.argv[2]
conf = {}
with open(env_file) as handle:
    for line in handle:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            conf[key.strip()] = value.strip()

host = conf.get("SMTP_HOST", "")
port = int(conf.get("SMTP_PORT") or 587)
user = conf.get("SMTP_USER", "")
password = conf.get("SMTP_PASSWORD", "")
sender = conf.get("SMTP_FROM", "") or user
to_addr = os.environ.get("ALERT_EMAIL") or conf.get("ALERT_EMAIL") or sender
security = (conf.get("SMTP_SECURITY") or "").lower()

if not host or not sender or not to_addr:
    print("cannot send: SMTP not configured (SMTP_HOST / SMTP_FROM missing)", file=sys.stderr)
    sys.exit(2)

try:
    detail = json.loads(payload)
except Exception:
    detail = {"raw": payload[:4000]}

failing = []
checks = detail.get("checks") if isinstance(detail, dict) else None
if isinstance(checks, dict):
    failing = [name for name, value in checks.items() if not value]
elif isinstance(checks, list):
    failing = [c.get("name", "?") for c in checks if not c.get("ok", True)]

body = "Concierge health check failed on 152.42.239.240.\n\n"
body += "Failing checks: " + (", ".join(failing) if failing else "see payload") + "\n\n"
body += json.dumps(detail, indent=2)[:6000] + "\n"

message = EmailMessage()
message["Subject"] = "ALERT: Concierge health check failing" + (f" ({', '.join(failing)})" if failing else "")
message["From"] = sender
message["To"] = to_addr
message.set_content(body)

if port == 465 or security in ("ssl", "smtps"):
    with smtplib.SMTP_SSL(host, port, timeout=25, context=ssl.create_default_context()) as server:
        if user:
            server.login(user, password)
        server.send_message(message)
else:
    with smtplib.SMTP(host, port, timeout=25) as server:
        server.starttls(context=ssl.create_default_context())
        if user:
            server.login(user, password)
        server.send_message(message)
print(f"alert sent to {to_addr}")
PY
status=$?
if [ $status -eq 0 ]; then echo "$now" > "$STAMP_FILE"; fi
exit $status
