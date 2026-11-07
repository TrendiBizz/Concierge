"""Email and SMS sending with honest status.

Every send returns one of:
  "sent"    the provider accepted it
  "queued"  no provider is configured yet; the message was only written to data/outbox.jsonl
  "failed"  a provider is configured but refused or could not be reached
The voice agent must only tell a caller "sent" when the status is "sent".

Email: any SMTP provider (Amazon SES, Postmark, Brevo, Gmail app password...).
  SMTP_HOST SMTP_PORT (587; 465 uses SSL) SMTP_USER SMTP_PASSWORD EMAIL_FROM
SMS: SMS_PROVIDER=mac sends from this Mac's Messages app through your iPhone (see sms_providers.py;
  outcome is read from Messages' database, so it can also return "unverified", which is NOT sent).
  Otherwise Telnyx REST API: TELNYX_API_KEY SMS_FROM (a real number; NZ does not allow sender IDs)
Both default to the outbox, so nothing is ever sent until you set the variables.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("trendi-notify")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))


def valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


def to_e164(number: str, default_cc: str = "64") -> str:
    """Normalise a spoken phone number to +E.164. Returns '' if it cannot be a real number."""
    raw = (number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        out = digits
    elif digits.startswith("00"):
        out = digits[2:]
    elif digits.startswith("0"):
        out = default_cc + digits[1:]
    else:
        out = digits
    return "+" + out if 8 <= len(out) <= 15 else ""


def _outbox(record: dict) -> None:
    path = _data_dir() / "outbox.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": datetime.now(timezone.utc).isoformat(), **record}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _send_email_sync(to: str, subject: str, body: str, ics_text: str | None) -> str:
    if not valid_email(to):
        return "failed"
    host = os.environ.get("SMTP_HOST", "")
    sender = os.environ.get("EMAIL_FROM", "")
    if not host or not sender:
        _outbox({"channel": "email", "to": to, "subject": subject, "body": body, "status": "queued"})
        return "queued"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body)
    if ics_text:
        msg.add_attachment(
            ics_text.encode("utf-8"), maintype="text", subtype="calendar", filename="trendi.ics"
        )
    port = int(os.environ.get("SMTP_PORT", "587"))
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls()
        with server:
            user = os.environ.get("SMTP_USER", "")
            if user:
                server.login(user, os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(msg)
    except Exception:  # noqa: BLE001 - never leak credentials in logs
        logger.warning("email send failed", exc_info=False)
        _outbox({"channel": "email", "to": to, "subject": subject, "body": body, "status": "failed"})
        return "failed"
    _outbox({"channel": "email", "to": to, "subject": subject, "status": "sent"})
    return "sent"


def _send_sms_mac(to_e164: str, body: str) -> str:
    """SMS through Messages.app on this Mac. Returns sent, failed or unverified."""
    from sms_providers import MacMessagesProvider

    try:
        wait = max(1, int(os.environ.get("SMS_VERIFY_SECONDS", "10")))
    except ValueError:
        wait = 10
    status = MacMessagesProvider(verify_seconds=wait)._send_sync(to_e164, body)
    _outbox({"channel": "sms", "to": to_e164, "body": body, "status": status})
    return status


def _send_sms_sync(to_e164: str, body: str) -> str:
    if not to_e164.startswith("+"):
        return "failed"
    if os.environ.get("SMS_PROVIDER", "").strip().lower() == "mac":
        return _send_sms_mac(to_e164, body)
    key = os.environ.get("TELNYX_API_KEY", "")
    sender = os.environ.get("SMS_FROM", "")
    if not key or not sender:
        _outbox({"channel": "sms", "to": to_e164, "body": body, "status": "queued"})
        return "queued"
    req = urllib.request.Request(
        "https://api.telnyx.com/v2/messages",
        data=json.dumps({"from": sender, "to": to_e164, "text": body}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
    except Exception:  # noqa: BLE001
        logger.warning("sms send failed", exc_info=False)
        ok = False
    _outbox({"channel": "sms", "to": to_e164, "body": body, "status": "sent" if ok else "failed"})
    return "sent" if ok else "failed"


async def send_email(to: str, subject: str, body: str, ics_text: str | None = None) -> str:
    return await asyncio.to_thread(_send_email_sync, to, subject, body, ics_text)


async def send_sms(to_e164: str, body: str) -> str:
    return await asyncio.to_thread(_send_sms_sync, to_e164, body)
