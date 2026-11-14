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

HERE="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1
payload=$(cat 2>/dev/null || true)
[ -z "$payload" ] && payload='{"status":"unknown","detail":"healthcheck produced no output"}'

python3 - "$ENV_FILE" "$payload" "$DRY_RUN" "$HERE" <<'PY'
import json, os, smtplib, ssl, sys
from email.message import EmailMessage

env_file, payload = sys.argv[1], sys.argv[2]
dry_run = len(sys.argv) > 3 and sys.argv[3] == "1"
# The payload arrives on stdin, so __file__ is "<stdin>": the script directory has to be passed in.
script_dir = sys.argv[4]
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
sender = conf.get("SMTP_FROM", "") or user or "alert@localhost"
to_addr = os.environ.get("ALERT_EMAIL") or conf.get("ALERT_EMAIL") or sender
security = (conf.get("SMTP_SECURITY") or "").lower()

if not dry_run and (not host or not sender or not to_addr):
    print("cannot send: SMTP not configured (SMTP_HOST / SMTP_FROM missing)", file=sys.stderr)
    sys.exit(2)

# The report's shape, the "is this even JSON" question and the wording all live in one tested
# place: alert_body.summarise(). Reading `checks` here (a key no report ever had) is why every
# mail said "Failing checks: see payload".
import importlib.util
_spec = importlib.util.spec_from_file_location("concierge_alert_body", os.path.join(script_dir, "alert_body.py"))
_alert_body = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_alert_body)
summary = _alert_body.summarise(payload)
failing = summary["failing"]
body = summary["body"]

message = EmailMessage()
message["Subject"] = "ALERT: Concierge health check failing" + summary["suffix"]
message["From"] = sender
message["To"] = to_addr
# Marks this as our own mail: the inbound pipeline drops it instead of turning a health alert into
# a customer enquiry and texting the owner a wall of RFC822 headers.
message["X-Concierge-Mail"] = "1"
message["Auto-Submitted"] = "auto-generated"
message.set_content(body)

if dry_run:
    # Proves what would be mailed without sending anything: the subject must name the check.
    print("Subject: " + str(message["Subject"]))
    print(body[:1200])
    sys.exit(0)

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
