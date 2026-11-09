#!/usr/bin/env bash
# Test the Mac SMS provider (Messages.app + iPhone Text Message Forwarding).
#
#   ./concierge-stack/tests/send-test-sms.sh --check
#       Sends NOTHING. Checks Messages can see an SMS service, and whether this
#       Terminal can read Messages' database (needed to confirm a send really worked).
#   ./concierge-stack/tests/send-test-sms.sh NUMBER
#       Sends ONE real SMS to that number. Use a DIFFERENT person's mobile, not your own:
#       texting your own number from your own number does not work as a test.
#       Prints only: sent, failed or unverified.
#
# Run it from a normal Terminal window on the Mac. The first run triggers a macOS prompt
# asking to let Terminal control Messages: click Allow. The number is never printed or logged.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 --check | NUMBER [message text]" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then echo "Missing $PY. Create the venv first (see README)." >&2; exit 1; fi

MODE="send"
NUMBER=""
TEXT="Trendi Concierge: SMS delivery test. If you can read this, texting from the Mac works."
if [[ "$1" == "--check" ]]; then
  MODE="check"
else
  NUMBER="$1"
  if [[ $# -ge 2 ]]; then TEXT="$2"; fi
fi

"$PY" - "$MODE" "$NUMBER" "$TEXT" "$DIR" <<'PY'
import asyncio
import sys

mode, number, text, base = sys.argv[1:5]
sys.path.insert(0, base + "/agent")
import notify
import sms_providers

provider = sms_providers.get_provider("mac")

if mode == "check":
    ok, reason = provider.check()
    print("sms service:", "ok" if ok else "not ready")
    print(reason)
    can, why = provider.can_verify()
    print("verification:", "on" if can else "off")
    print(why)
    sys.exit(0 if ok and can else 1)

to = notify.to_e164(number)
if not to:
    print("That does not look like a real phone number. Nothing was sent.")
    sys.exit(1)

ok, reason = provider.check()
if not ok:
    print("Not sending. " + reason)
    sys.exit(1)

can, why = provider.can_verify()
if not can:
    print("Warning: " + why)
    print("The text will still be attempted, but the result can only be 'unverified'.")

status = asyncio.run(provider.send(to, text))
print("sms status:", status)
if status == "sent":
    print("Messages confirmed the text left. Look at the other phone to confirm it arrived and is a green SMS.")
elif status == "failed":
    print("The text failed. Check the Messages app for a red 'Not Delivered' note and run with --check.")
else:
    print("UNVERIFIED: the command ran but the outcome could not be read. Do NOT count this as sent.")
    print("Look at the Messages app and the other phone to see what really happened.")
sys.exit(0 if status == "sent" else 1)
PY
