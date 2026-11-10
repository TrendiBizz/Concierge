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

from . import channel_authorization, db, email_auth, email_risk, inbound_email, inbound_policy
from .config import get_settings

ADDRESS = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
MAX_BYTES = 800_000
REQUIRED_FIELDS = {"message_id", "recipient", "sender", "subject", "text"}
OPTIONAL_FIELDS = {"auth", "reply_to", "size", "has_attachments", "raw_b64"}
AUTH_KEYS = {"spf", "dkim", "dmarc", "authentication_results", "reply_to", "content_type"}
MAILBOX_HOURLY_LIMIT = 60
SENDER_HOURLY_LIMIT = 10


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
        if not REQUIRED_FIELDS <= set(payload) <= REQUIRED_FIELDS | OPTIONAL_FIELDS:
            raise ValueError("Invalid fields")
        recipient = normalize_recipient(payload["recipient"])
        if not all(isinstance(payload[k], str) for k in ("message_id", "sender", "subject", "text")):
            raise ValueError("Invalid field types")
        if len(payload["sender"]) > 320 or len(payload["subject"]) > 250:
            raise ValueError("Invalid fields")
        auth = payload.get("auth")
        if auth is not None:
            if not isinstance(auth, dict) or len(auth) > 10:
                raise ValueError("Invalid auth results")
            auth = {k: v[:500] for k, v in auth.items()
                    if k in AUTH_KEYS and isinstance(v, str)}
        reply_to = payload.get("reply_to")
        if reply_to is not None and (not isinstance(reply_to, str) or len(reply_to) > 320):
            raise ValueError("Invalid reply-to")
        size = payload.get("size")
        if size is not None and (not isinstance(size, int) or size < 0 or size > 10_000_000):
            raise ValueError("Invalid size")
        has_attachments = payload.get("has_attachments")
        if has_attachments is not None and not isinstance(has_attachments, bool):
            raise ValueError("Invalid attachment flag")
        raw_b64 = payload.get("raw_b64")
        if raw_b64 is not None and (not isinstance(raw_b64, str)
                                    or len(raw_b64) > email_auth.MAX_RAW_B64):
            raise ValueError("Invalid raw message")
        mailbox = await db.pool().fetchrow(
            "SELECT tenant_id FROM inbound_mailboxes WHERE recipient=$1 AND provider='cloudflare' AND enabled",
            recipient,
        )
        if not mailbox:
            raise HTTPException(404, "Unknown mailbox")
        if not await channel_authorization.is_authorized(mailbox["tenant_id"], "email_read"):
            raise HTTPException(403, "Business has not authorized inbound email")
        # Per-mailbox flood limit and per-sender limit. The sender limit does not
        # reject mail (which would lose it); it quarantines for human review.
        tenant_id = mailbox["tenant_id"]
        policy = await inbound_policy.rule_for(tenant_id, payload["sender"])
        if policy == "block":
            # Accept and drop: never bounce to a possibly spoofed address.
            return {"accepted": True, "dropped": "blocked"}
        # Cryptographic DKIM + DMARC alignment from the Rust sidecar. Failures
        # fall back to the header hints; they never block ingestion.
        if raw_b64:
            verified = await email_auth.verify(raw_b64)
            if verified:
                auth = email_auth.merge(auth, verified)
        recent = await db.pool().fetchval(
            "SELECT count(*) FROM email_drafts WHERE tenant_id=$1 "
            "AND created_at > now() - interval '1 hour'", tenant_id)
        if recent >= MAILBOX_HOURLY_LIMIT:
            raise HTTPException(429, "Too many inbound emails")
        sender_recent = await db.pool().fetchval(
            "SELECT count(*) FROM email_drafts WHERE tenant_id=$1 "
            "AND lower(sender)=lower($2) AND created_at > now() - interval '1 hour'",
            tenant_id, payload["sender"])
        assessment = email_risk.assess(
            auth, payload["sender"], reply_to, payload["subject"], payload["text"],
            size=size, has_attachments=bool(has_attachments))
        flags = list(assessment["flags"])
        risk = assessment["risk"]
        if sender_recent >= SENDER_HOURLY_LIMIT:
            flags.append("sender_rate_limited")
            risk = "high"
        if policy == "allow":
            # A listed sender still gets risk flags, but not quarantine.
            risk = "medium" if risk == "high" else risk
        draft = await inbound_email.ingest_verified(
            tenant_id, "cloudflare", payload["message_id"],
            payload["sender"], recipient, payload["subject"], payload["text"],
            auth=auth, risk=risk, flags=flags,
        )
    except (ValueError, TypeError, inbound_email.InboundError) as exc:
        raise HTTPException(400, "Invalid email payload") from exc
    return {"accepted": True, "draft_id": draft["id"]}
