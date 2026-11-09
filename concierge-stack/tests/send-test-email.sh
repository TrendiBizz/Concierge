#!/usr/bin/env bash
# Send ONE real test email through agent/notify.py using the SMTP settings in .env.
# Prints only the status: sent, queued (no SMTP configured) or failed. Never prints credentials.
# Usage: ./concierge-stack/tests/send-test-email.sh you@example.com
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 recipient@example.com" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$DIR/.env" ]]; then echo "Run set-email.sh first." >&2; exit 1; fi

set -a
# shellcheck disable=SC1091
source "$DIR/.env"
set +a

# A throwaway data dir so the test does not pollute data/outbox.jsonl.
export DATA_DIR
DATA_DIR="$(mktemp -d)"

"$DIR/.venv/bin/python" - "$1" "$DIR" <<'PY'
import asyncio
import sys

sys.path.insert(0, sys.argv[2] + "/agent")
import notify

status = asyncio.run(
    notify.send_email(
        sys.argv[1],
        "Trendi Concierge: email delivery test",
        "This is a test message from the Trendi Concierge stack. If you can read it, "
        "Brevo SMTP delivery works.",
    )
)
print("email status:", status)
if status == "queued":
    print("No SMTP_HOST or EMAIL_FROM is set, so nothing was sent.")
elif status == "failed":
    print("Brevo refused it or could not be reached. Check the login, SMTP key and verified sender.")
else:
    print("Brevo accepted it. Check the inbox (and spam) to confirm it really arrived.")
PY
