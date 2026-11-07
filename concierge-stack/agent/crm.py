"""Sends every recorded call (a message or a booking) to the CRM, which is Twenty, through the lead bridge.

The lead bridge is the small server that takes `POST /lead` and creates or finds the person in Twenty and attaches the
enquiry as a note (Concierge platform: integrations/twenty/bridge). It de-duplicates, so sending the same person twice is safe.

Same honesty rule as notify.py. push_lead returns exactly one of:
  "sent"    the bridge accepted it (200 with ok true; a duplicate counts, the CRM already has the person)
  "queued"  CRM_BRIDGE_URL is not set, so it was only written to data/outbox.jsonl
  "failed"  the bridge refused it, was unreachable, or there was no phone number or email to identify the person
Nothing here ever raises: a CRM outage must never break a call. The owner alert email still goes out.

Setting: CRM_BRIDGE_URL, for example http://127.0.0.1:4410/lead
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

import notify

logger = logging.getLogger("trendi-crm")


def _split_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split(None, 1)
    if not parts:
        return "Unknown", "caller"
    return parts[0], parts[1] if len(parts) > 1 else ""


def _post(url: str, payload: dict) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
            return "sent" if resp.status == 200 and body.get("ok") else "failed"
    except urllib.error.HTTPError as exc:
        logger.warning("crm push refused (HTTP %s)", exc.code)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        logger.warning("crm push failed (bridge unreachable or bad reply)")
    return "failed"


def push_lead_sync(*, name: str, phone: str, email: str, message: str, plan: str, source: str) -> str:
    to_phone = notify.to_e164(phone)
    to_email = (email or "").strip()
    who = to_phone or to_email
    record = {"channel": "crm", "to": who or "unknown", "subject": source, "body": message}
    if not who:
        notify._outbox({**record, "status": "failed"})
        return "failed"
    url = os.environ.get("CRM_BRIDGE_URL", "").strip()
    if not url:
        notify._outbox({**record, "status": "queued"})
        return "queued"
    first, last = _split_name(name)
    payload = {
        "first_name": first,
        "last_name": last,
        "email": to_email if notify.valid_email(to_email) else "",
        "phone": to_phone,
        "message": message,
        "plan": plan,
        "source": source,
    }
    status = _post(url, {k: v for k, v in payload.items() if v != ""})
    notify._outbox({**record, "status": status})
    return status


async def push_lead(
    *, name: str, phone: str, email: str = "", message: str = "", plan: str = "", source: str = "Voice call"
) -> str:
    try:
        return await asyncio.to_thread(
            push_lead_sync, name=name, phone=phone, email=email, message=message, plan=plan, source=source
        )
    except Exception:  # noqa: BLE001 - a CRM problem must never break a call
        logger.exception("crm push crashed")
        return "failed"
