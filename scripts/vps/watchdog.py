"""Dead-man's switch for the health check.

The health check runs from cron every five minutes. If it stops running — it crashes on a bug we just
introduced, Python breaks, the host's cron dies — nothing tells anybody: the last good status simply
stays on disk. I did exactly that on 13 Nov 2026 by deploying a health check with a TypeError; every run
would have failed and alerting would have been silent.

This script is deliberately separate and dependency-free: it reads the timestamp in status.json and
mails once if the check has not completed recently. It does not import the health check, so a fault
there cannot silence the watchdog too.
"""
from __future__ import annotations

import json
import os
import pathlib
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage

STATUS = pathlib.Path("/opt/trendi/monitoring/status.json")
STATE = pathlib.Path("/opt/trendi/monitoring/watchdog.json")
ENV = pathlib.Path("/opt/trendi/shared/healthcheck.env")
STALE_MINUTES = int(os.environ.get("WATCHDOG_STALE_MINUTES", "15"))


def load_env() -> dict:
    values = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def send(env: dict, subject: str, body: str) -> str:
    host = env.get("SMTP_HOST", "")
    if not host:
        return "not sent (no SMTP_HOST)"
    message = EmailMessage()
    message["From"] = env.get("ALERT_FROM") or env.get("SMTP_USER", "alerts@trendibizz.com")
    message["To"] = env.get("ALERT_TO", "")
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, int(env.get("SMTP_PORT", "587")), timeout=20) as server:
        server.starttls(context=context)
        if env.get("SMTP_USER"):
            server.login(env["SMTP_USER"], env.get("SMTP_PASS", ""))
        server.send_message(message)
    return "sent"


def last_checked() -> datetime | None:
    try:
        data = json.loads(STATUS.read_text())
        return datetime.fromisoformat(data["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main() -> int:
    now = datetime.now(timezone.utc)
    checked = last_checked()
    age = (now - checked).total_seconds() / 60 if checked else None
    if age is not None and age <= STALE_MINUTES:
        print(f"{now.isoformat()} watchdog: healthy ({age:.0f} min since last check)")
        return 0

    message = (f"The health check has not completed for "
               f"{'an unknown time' if age is None else f'{age:.0f} minutes'}"
               f" (expected every 5). Last checked: {checked.isoformat() if checked else 'never'}. "
               f"Alerting may be silent. Run: python3 scripts/vps/healthcheck.py --no-alert")
    if "--dry-run" in sys.argv:
        print(f"{now.isoformat()} watchdog: STALE - would email: {message}")
        return 1
    if os.environ.get("WATCHDOG_NO_MAIL"):
        print(f"{now.isoformat()} watchdog: STALE - mail suppressed: {message}")
        return 1
    try:
        print(f"{now.isoformat()} watchdog: STALE -> {send(load_env(), '[Concierge FAIL] health check has stopped running', message)}")
    except Exception as exc:  # noqa: BLE001 - report, never crash the watchdog
        print(f"{now.isoformat()} watchdog: STALE but could not send: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
