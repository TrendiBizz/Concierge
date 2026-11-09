#!/usr/bin/env bash
# Stop only this local stack; retain its database, credentials and business data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TRENDI_WEBSITE="${TRENDI_WEBSITE:-$(dirname "$ROOT")/trendi-site-web}"
cd "$ROOT"
docker compose --env-file /dev/null -f scripts/local/compose.yml stop
python3 - <<'PY'
import os
from pathlib import Path
import signal
import subprocess

root = Path.cwd()
path = root / '.private/local-stack/social.pid'
if path.exists():
    pid = int(path.read_text())
    expected = str(root / 'concierge-stack/social-service/target/debug/concierge-social')
    command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                             capture_output=True, text=True).stdout.strip()
    if command == expected:
        os.kill(pid, signal.SIGTERM)
        path.unlink()
    elif command:
        raise SystemExit('PID belongs to another process; it was left running.')
print('Local stack stopped; local data and all existing public services preserved.')
PY
