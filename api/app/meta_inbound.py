"""N7 Messaging Expansion: WhatsApp Business Cloud API, Facebook Messenger, and Instagram DM inbound.

Ships DISABLED by default (`META_MESSAGING_ENABLED=false`) until Meta Business app review,
app secret, and webhook verify token are supplied. Every webhook POST verifies Meta's
`X-Hub-Signature-256` HMAC-SHA256 before touching any database row.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import crypto_vault, db, owner_auth
from .config import get_settings

owner_router = APIRouter(prefix="/owner/meta-messaging", tags=["meta-messaging"])
webhook_router = APIRouter(prefix="/webhooks/meta", tags=["meta-messaging"])

META_CHANNELS = ("whatsapp", "messenger", "instagram")


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.meta_messaging_enabled and (s.meta_app_secret or "").strip() and (s.meta_webhook_verify_token or "").strip())


def _verify_hub_signature(payload: bytes, header_value: str, secret: str) -> bool:
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_value, expected)


def parse_meta_events(body: dict) -> list[dict]:
    """Extract normalized inbound messages from WhatsApp, FB Messenger, or IG DM webhook payloads."""
    obj = str(body.get("object") or "").lower()
    events: list[dict] = []
    for entry in body.get("entry") or []:
        if obj == "whatsapp_business_account":
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                phone_id = str((val.get("metadata") or {}).get("phone_number_id") or "")
                contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in (val.get("contacts") or [])}
                for msg in val.get("messages") or []:
                    text = (msg.get("text") or {}).get("body") or ""
                    sender = str(msg.get("from") or "")
                    if phone_id and sender and text:
                        events.append({
                            "channel": "whatsapp",
                            "external_id": phone_id,
                            "external_message_id": str(msg.get("id") or ""),
                            "sender_id": sender,
                            "sender_name": contacts.get(sender, ""),
                            "text": text[:4000],
                        })
        elif obj in ("page", "instagram"):
            ch = "messenger" if obj == "page" else "instagram"
            page_id = str(entry.get("id") or "")
            for m in entry.get("messaging") or []:
                msg = m.get("message") or {}
                if msg.get("is_echo"):
                    continue
                text = str(msg.get("text") or "")
                sender = str((m.get("sender") or {}).get("id") or "")
                if page_id and sender and text:
                    events.append({
                        "channel": ch,
                        "external_id": page_id,
                        "external_message_id": str(msg.get("mid") or ""),
                        "sender_id": sender,
                        "sender_name": "",
                        "text": text[:4000],
                    })
    return events


@webhook_router.get("/messaging", response_class=PlainTextResponse)
async def meta_webhook_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    if not is_enabled():
        raise HTTPException(503, "Meta messaging is disabled on this server")
    expected = get_settings().meta_webhook_verify_token
    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, expected):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Invalid verify token")


@webhook_router.post("/messaging")
async def meta_webhook_inbound(request: Request):
    if not is_enabled():
        raise HTTPException(503, "Meta messaging is disabled on this server")
    payload = await request.body()
    sig = request.headers.get("x-hub-signature-256") or ""
    if not _verify_hub_signature(payload, sig, get_settings().meta_app_secret):
        raise HTTPException(401, "Invalid X-Hub-Signature-256")
    try:
        body = json.loads(payload.decode("utf-8"))
    except ValueError:
        raise HTTPException(400, "Invalid JSON") from None

    stored = 0
    for ev in parse_meta_events(body):
        ch_row = await db.pool().fetchrow(
            "SELECT tenant_id FROM tenant_meta_channels WHERE channel=$1 AND external_id=$2 AND enabled",
            ev["channel"], ev["external_id"],
        )
        if not ch_row:
            continue
        ext_mid = ev["external_message_id"] or hashlib.sha256(
            f"{ev['channel']}:{ev['sender_id']}:{ev['text']}".encode()
        ).hexdigest()
        res = await db.pool().execute(
            """INSERT INTO meta_inbound_messages(
                   tenant_id, channel, external_message_id, sender_id, sender_name, text, direction)
               VALUES($1, $2, $3, $4, $5, $6, 'in')
               ON CONFLICT (channel, external_message_id) DO NOTHING""",
            ch_row["tenant_id"], ev["channel"], ext_mid, ev["sender_id"], ev["sender_name"], ev["text"],
        )
        if res.endswith(" 1"):
            stored += 1
    return {"ok": True, "stored": stored}


# ---- Owner endpoints ------------------------------------------------------------------------
@owner_router.get("")
async def owner_meta_overview(user: dict = Depends(owner_auth.current_user)):
    enabled = is_enabled()
    channels = await db.pool().fetch(
        "SELECT id, channel, external_id, enabled, created_at FROM tenant_meta_channels "
        "WHERE tenant_id=$1 ORDER BY created_at DESC",
        user["tenant_id"],
    )
    messages = await db.pool().fetch(
        "SELECT id, channel, sender_id, sender_name, text, direction, created_at "
        "FROM meta_inbound_messages WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 50",
        user["tenant_id"],
    )
    return {
        "platform_enabled": enabled,
        "unavailable_reason": "" if enabled else "needs Meta Business app approval, META_MESSAGING_ENABLED=true, META_APP_SECRET, and META_WEBHOOK_VERIFY_TOKEN",
        "channels": [{**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in channels],
        "messages": [{**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in messages],
    }


class MetaChannelBind(BaseModel):
    channel: Literal["whatsapp", "messenger", "instagram"]
    external_id: str = Field(min_length=3, max_length=120)
    access_token: str = Field(min_length=8, max_length=2048)


@owner_router.post("/channels", status_code=201)
async def owner_bind_meta_channel(body: MetaChannelBind, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not is_enabled():
        raise HTTPException(409, "Meta messaging is disabled until Meta Business approval and credentials are configured")
    enc = crypto_vault.encrypt_text(body.access_token.strip(), aad=f"meta:{user['tenant_id']}:{body.channel}")
    row = await db.pool().fetchrow(
        """INSERT INTO tenant_meta_channels(tenant_id, channel, external_id, access_token_enc, enabled)
           VALUES($1, $2, $3, $4, true)
           ON CONFLICT (channel, external_id) DO UPDATE SET access_token_enc=$4, enabled=true
           WHERE tenant_meta_channels.tenant_id=$1
           RETURNING id, channel, external_id, enabled, created_at""",
        user["tenant_id"], body.channel, body.external_id.strip(), enc,
    )
    if not row:
        raise HTTPException(409, "That channel ID is already bound to another workspace")
    return {**dict(row), "id": str(row["id"]), "created_at": row["created_at"].isoformat()}


@owner_router.delete("/channels/{channel_id}")
async def owner_delete_meta_channel(channel_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    res = await db.pool().execute(
        "DELETE FROM tenant_meta_channels WHERE id=$1 AND tenant_id=$2",
        channel_id, user["tenant_id"],
    )
    if res.endswith("0"):
        raise HTTPException(404, "Channel not found")
    return {"ok": True}
