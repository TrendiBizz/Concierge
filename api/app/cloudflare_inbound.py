"""Cloudflare Email Worker ingress.

The Worker authenticates to the API with a pre-shared HMAC key. Cloudflare
routing and signing keys must be configured independently before enabling.
An authenticated Worker is not evidence that the sender is trustworthy.
"""
import hashlib
import hmac
import json
import re
import time

from fastapi import HTTPException, Request

from . import db, inbound_email
from .config import get_settings

ADDRESS = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
MAX_BYTES = 30000


def normalize_recipient(address: str) -> str:
    if not isinstance(address, str):
        raise ValueError("Invalid mailbox")
    value = address.strip().lower()
    if len(value) > 320 or not ADDRESS.fullmatch(value):
        raise ValueError("Invalid mailbox")
    return value


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


async def register_mailbox(tenant_id, recipient: str, enabled: bool = False) -> None:
    address = normalize_recipient(recipient)
    # Fail closed on conflicts. Another tenant's mailbox cannot be claimed.
    result = await db.pool().execute(
        """INSERT INTO inbound_mailboxes(recipient,tenant_id,provider,enabled)
           VALUES($1,$2,'cloudflare',$3)
           ON CONFLICT(recipient) DO UPDATE SET enabled=EXCLUDED.enabled
           WHERE inbound_mailboxes.tenant_id=EXCLUDED.tenant_id
             AND inbound_mailboxes.provider=EXCLUDED.provider""",
        address, tenant_id, enabled,
    )
    if result != "INSERT 0 1":
        raise ValueError("Mailbox is assigned elsewhere")


async def handle(request: Request) -> dict:
    settings = get_settings()
    if not settings.inbound_cloudflare_enabled or len(settings.inbound_cloudflare_secret) < 32:
        raise HTTPException(503, "Inbound email is disabled")
    timestamp = request.headers.get("x-concierge-timestamp", "")
    supplied = request.headers.get("x-concierge-signature", "")
    if not timestamp.isdecimal() or len(timestamp) > 12 or not re.fullmatch(r"[a-f0-9]{64}", supplied):
        raise HTTPException(401, "Invalid signature")
    if abs(int(time.time()) - int(timestamp)) > 300:
        raise HTTPException(401, "Expired signature")
    # Reject oversized messages even without Content-Length; no MIME/attachments stored.
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(413, "Email payload too large")
    expected = signature(settings.inbound_cloudflare_secret, timestamp, body)
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid signature")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Invalid payload")
        if set(payload) != {"message_id", "recipient", "sender", "subject", "text"}:
            raise ValueError("Invalid fields")
        recipient = normalize_recipient(payload["recipient"])
        if not all(isinstance(payload[k], str) for k in ("message_id", "sender", "subject", "text")):
            raise ValueError("Invalid field types")
        if len(payload["sender"]) > 320 or len(payload["subject"]) > 250:
            raise ValueError("Invalid fields")
        mailbox = await db.pool().fetchrow(
            "SELECT tenant_id FROM inbound_mailboxes WHERE recipient=$1 AND provider='cloudflare' AND enabled",
            recipient,
        )
        if not mailbox:
            raise HTTPException(404, "Unknown mailbox")
        draft = await inbound_email.ingest_verified(
            mailbox["tenant_id"], "cloudflare", payload["message_id"],
            payload["sender"], recipient, payload["subject"], payload["text"],
        )
    except (ValueError, TypeError, inbound_email.InboundError) as exc:
        raise HTTPException(400, "Invalid email payload") from exc
    return {"accepted": True, "draft_id": draft["id"]}
