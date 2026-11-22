"""N7 Messaging Expansion: WhatsApp Business Cloud API, Facebook Messenger, and Instagram DM.

Handles:
- Meta webhook GET verification and X-Hub-Signature-256 verified POST ingestion
- Per-tenant Page / Instagram / WhatsApp channel binding with N9 encrypted tokens
- Automatic sync & webhook unsubscribe with Facebook/Instagram OAuth in Social
- WhatsApp Embedded Signup (Facebook Login for Business, gated behind META_WA_EMBEDDED_SIGNUP_CONFIG_ID)
- Outbound replies from the Studio Inbox within Meta's 24-hour customer service window
  (and approved WhatsApp templates outside 24 hours when templates exist)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import crypto_vault, db, owner_auth
from .config import get_settings

owner_router = APIRouter(prefix="/owner/meta-messaging", tags=["meta-messaging"])
webhook_router = APIRouter(prefix="/webhooks/meta", tags=["meta-messaging"])

META_CHANNELS = ("whatsapp", "messenger", "instagram")
META_WEBHOOK_FIELDS = "messages,messaging_postbacks"
WINDOW_HOURS = 24
_DIGITS_RE = re.compile(r"^[0-9]{5,40}$")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
_LANG_CODE_RE = re.compile(r"^[a-zA-Z]{2,3}(?:_[A-Za-z0-9]{2,4})?$")
_WA_STATE_TTL = 600
_WA_USED_NONCES: dict[str, float] = {}


def is_enabled() -> bool:
    s = get_settings()
    return bool(
        s.meta_messaging_enabled
        and (s.meta_app_secret or "").strip()
        and (s.meta_webhook_verify_token or "").strip()
    )


def graph_base_url() -> str:
    ver = (get_settings().meta_graph_version or "v22.0").strip()
    if not ver.startswith("v"):
        ver = "v22.0"
    return f"https://graph.facebook.com/{ver}"


def wa_embedded_signup_info() -> dict:
    s = get_settings()
    app_id = (s.meta_app_id or "").strip()
    config_id = (s.meta_wa_embedded_signup_config_id or "").strip()
    enabled = bool(is_enabled() and app_id and config_id)
    missing: list[str] = []
    if not is_enabled():
        missing.append("META_MESSAGING_ENABLED / META_APP_SECRET / META_WEBHOOK_VERIFY_TOKEN")
    if not app_id:
        missing.append("META_APP_ID")
    if not config_id:
        missing.append("META_WA_EMBEDDED_SIGNUP_CONFIG_ID")
    return {
        "enabled": enabled,
        "unavailable_reason": "" if enabled else (
            "WhatsApp Embedded Signup requires " + ", ".join(missing)
            + " (create a Facebook Login for Business configuration in the Meta App Dashboard)."
        ),
    }


def _verify_hub_signature(payload: bytes, header_value: str, secret: str) -> bool:
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_value, expected)


async def _graph_request(
    method: str,
    path: str,
    *,
    token: str = "",
    params: dict | None = None,
    json_body: dict | None = None,
    form_body: dict | None = None,
) -> tuple[int, dict]:
    """Single Meta Graph API HTTP helper (isolated for clean mocking in tests)."""
    url = graph_base_url() + "/" + path.lstrip("/")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            resp = await client.request(
                method, url, headers=headers, params=params, json=json_body, data=form_body,
            )
    except httpx.HTTPError:
        raise HTTPException(502, "Meta Graph API is temporarily unreachable") from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return resp.status_code, data if isinstance(data, dict) else {}


def _make_wa_state(tenant_id: str) -> str:
    secret = (get_settings().meta_app_secret or "").strip()
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    msg = f"wa:{tenant_id}:{ts}:{nonce}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{nonce}.{sig}"


def _consume_wa_state(state: str, tenant_id: str) -> None:
    now = time.time()
    # Prune expired nonces
    for k, exp in list(_WA_USED_NONCES.items()):
        if exp <= now:
            _WA_USED_NONCES.pop(k, None)
    parts = (state or "").split(".")
    if len(parts) != 3:
        raise HTTPException(400, "Invalid or expired WhatsApp signup state")
    ts_str, nonce, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        raise HTTPException(400, "Invalid or expired WhatsApp signup state") from None
    if now - ts > _WA_STATE_TTL or ts - now > 60:
        raise HTTPException(400, "WhatsApp signup state expired; please try again")
    secret = (get_settings().meta_app_secret or "").strip()
    expected = hmac.new(
        secret.encode("utf-8"),
        f"wa:{tenant_id}:{ts_str}:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Invalid WhatsApp signup state")
    if nonce in _WA_USED_NONCES:
        raise HTTPException(400, "WhatsApp signup state already used")
    _WA_USED_NONCES[nonce] = now + _WA_STATE_TTL


def parse_meta_events(body: dict) -> list[dict]:
    """Extract normalized inbound messages & postbacks from WhatsApp, FB Messenger, or IG DM webhooks."""
    obj = str(body.get("object") or "").lower()
    events: list[dict] = []
    for entry in body.get("entry") or []:
        if obj == "whatsapp_business_account":
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                phone_id = str((val.get("metadata") or {}).get("phone_number_id") or "")
                contacts = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                    for c in (val.get("contacts") or [])
                }
                for msg in val.get("messages") or []:
                    text = (msg.get("text") or {}).get("body") or ""
                    if not text and msg.get("button"):
                        text = str((msg.get("button") or {}).get("text") or "")
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
                postback = m.get("postback") or {}
                text = str(msg.get("text") or postback.get("title") or postback.get("payload") or "")
                mid = str(msg.get("mid") or postback.get("mid") or "")
                sender = str((m.get("sender") or {}).get("id") or "")
                if page_id and sender and text:
                    events.append({
                        "channel": ch,
                        "external_id": page_id,
                        "external_message_id": mid,
                        "sender_id": sender,
                        "sender_name": "",
                        "text": text[:4000],
                    })
    return events


async def sync_social_meta_channels(tenant_id, channels: list[dict]) -> int:
    """Persist Messenger/Instagram Page/IG grants from Social OAuth into tenant_meta_channels."""
    stored = 0
    for ch in channels or []:
        channel = str(ch.get("channel") or "").strip().lower()
        external_id = str(ch.get("external_id") or "").strip()
        access_token = str(ch.get("access_token") or "").strip()
        if channel not in ("messenger", "instagram") or not external_id or not access_token:
            continue
        page_id = str(ch.get("page_id") or (external_id if channel == "messenger" else "")).strip()
        display_name = str(ch.get("display_name") or "").strip()[:200]
        social_account_id = str(ch.get("account_id") or "").strip()[:128]
        subscribed = bool(ch.get("webhook_subscribed"))
        enc = crypto_vault.encrypt_text(access_token, aad=f"meta:{tenant_id}:{channel}")
        row = await db.pool().fetchrow(
            """INSERT INTO tenant_meta_channels(
                   tenant_id, channel, external_id, page_id, display_name,
                   social_account_id, webhook_subscribed, access_token_enc, enabled)
               VALUES($1, $2, $3, $4, $5, $6, $7, $8, true)
               ON CONFLICT (channel, external_id) DO UPDATE SET
                   page_id=EXCLUDED.page_id,
                   display_name=EXCLUDED.display_name,
                   social_account_id=EXCLUDED.social_account_id,
                   webhook_subscribed=EXCLUDED.webhook_subscribed,
                   access_token_enc=EXCLUDED.access_token_enc,
                   enabled=true
               WHERE tenant_meta_channels.tenant_id=$1
               RETURNING id""",
            tenant_id, channel, external_id, page_id, display_name,
            social_account_id, subscribed, enc,
        )
        if row:
            stored += 1
    return stored


async def _unsubscribe_channel_row(row: dict, tenant_id) -> None:
    """Best-effort unsubscribe Page or WABA webhooks if no sibling channel uses the same target."""
    channel = row["channel"]
    target_id = row["waba_id"] if channel == "whatsapp" else row["page_id"]
    if not target_id:
        return
    col = "waba_id" if channel == "whatsapp" else "page_id"
    sibling = await db.pool().fetchval(
        f"SELECT COUNT(*) FROM tenant_meta_channels "
        f"WHERE tenant_id=$1 AND {col}=$2 AND id <> $3 AND enabled",
        tenant_id, target_id, row["id"],
    )
    if sibling:
        return
    try:
        token = crypto_vault.decrypt_text(row["access_token_enc"], aad=f"meta:{tenant_id}:{channel}")
    except ValueError:
        return
    try:
        await _graph_request("DELETE", f"{target_id}/subscribed_apps", token=token)
    except HTTPException:
        pass


async def unsubscribe_and_remove_social_channels(tenant_id, network: str, social_account_id: str) -> int:
    """Unsubscribe and remove Meta messaging channel(s) when a Social account is disconnected."""
    channel = "messenger" if network == "facebook" else "instagram"
    rows = await db.pool().fetch(
        """SELECT id, channel, external_id, page_id, waba_id, access_token_enc
           FROM tenant_meta_channels
           WHERE tenant_id=$1 AND channel=$2 AND social_account_id=$3""",
        tenant_id, channel, social_account_id,
    )
    removed = 0
    for row in rows:
        await _unsubscribe_channel_row(dict(row), tenant_id)
        await db.pool().execute(
            "DELETE FROM tenant_meta_channels WHERE id=$1 AND tenant_id=$2",
            row["id"], tenant_id,
        )
        removed += 1
    return removed


# ---- Webhook endpoints ----------------------------------------------------------------------
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
                   tenant_id, channel, channel_external_id, external_message_id,
                   sender_id, sender_name, text, direction)
               VALUES($1, $2, $3, $4, $5, $6, $7, 'in')
               ON CONFLICT (channel, external_message_id) DO NOTHING""",
            ch_row["tenant_id"], ev["channel"], ev["external_id"], ext_mid,
            ev["sender_id"], ev["sender_name"], ev["text"],
        )
        if res.endswith(" 1"):
            stored += 1
    return {"ok": True, "stored": stored}


# ---- Owner overview & channel management ----------------------------------------------------
@owner_router.get("")
async def owner_meta_overview(user: dict = Depends(owner_auth.current_user)):
    enabled = is_enabled()
    channels = await db.pool().fetch(
        """SELECT id, channel, external_id, page_id, waba_id, display_name,
                  webhook_subscribed, enabled, created_at
           FROM tenant_meta_channels
           WHERE tenant_id=$1 ORDER BY created_at DESC""",
        user["tenant_id"],
    )
    messages = await db.pool().fetch(
        """SELECT id, channel, channel_external_id, sender_id, sender_name,
                  text, template_name, direction, created_at
           FROM meta_inbound_messages
           WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 50""",
        user["tenant_id"],
    )
    return {
        "platform_enabled": enabled,
        "unavailable_reason": "" if enabled else (
            "needs Meta Business app approval, META_MESSAGING_ENABLED=true, "
            "META_APP_SECRET, and META_WEBHOOK_VERIFY_TOKEN"
        ),
        "wa_embedded_signup": wa_embedded_signup_info(),
        "channels": [{**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in channels],
        "messages": [{**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in messages],
    }


class MetaChannelBind(BaseModel):
    channel: Literal["whatsapp", "messenger", "instagram"]
    external_id: str = Field(min_length=3, max_length=120)
    access_token: str = Field(min_length=8, max_length=2048)
    page_id: str = Field(default="", max_length=120)
    waba_id: str = Field(default="", max_length=120)
    display_name: str = Field(default="", max_length=200)


@owner_router.post("/channels", status_code=201)
async def owner_bind_meta_channel(body: MetaChannelBind, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not is_enabled():
        raise HTTPException(409, "Meta messaging is disabled until Meta Business approval and credentials are configured")
    enc = crypto_vault.encrypt_text(body.access_token.strip(), aad=f"meta:{user['tenant_id']}:{body.channel}")
    page_id = body.page_id.strip() or (body.external_id.strip() if body.channel == "messenger" else "")
    row = await db.pool().fetchrow(
        """INSERT INTO tenant_meta_channels(
               tenant_id, channel, external_id, page_id, waba_id, display_name, access_token_enc, enabled)
           VALUES($1, $2, $3, $4, $5, $6, $7, true)
           ON CONFLICT (channel, external_id) DO UPDATE SET
               page_id=EXCLUDED.page_id,
               waba_id=EXCLUDED.waba_id,
               display_name=EXCLUDED.display_name,
               access_token_enc=EXCLUDED.access_token_enc,
               enabled=true
           WHERE tenant_meta_channels.tenant_id=$1
           RETURNING id, channel, external_id, page_id, waba_id, display_name, webhook_subscribed, enabled, created_at""",
        user["tenant_id"], body.channel, body.external_id.strip(),
        page_id, body.waba_id.strip(), body.display_name.strip(), enc,
    )
    if not row:
        raise HTTPException(409, "That channel ID is already bound to another workspace")
    return {**dict(row), "id": str(row["id"]), "created_at": row["created_at"].isoformat()}


@owner_router.delete("/channels/{channel_id}")
async def owner_delete_meta_channel(channel_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        """SELECT id, channel, external_id, page_id, waba_id, access_token_enc
           FROM tenant_meta_channels WHERE id=$1 AND tenant_id=$2""",
        channel_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Channel not found")
    await _unsubscribe_channel_row(dict(row), user["tenant_id"])
    await db.pool().execute(
        "DELETE FROM tenant_meta_channels WHERE id=$1 AND tenant_id=$2",
        channel_id, user["tenant_id"],
    )
    return {"ok": True}


# ---- WhatsApp Embedded Signup (Facebook Login for Business) ---------------------------------
@owner_router.post("/whatsapp/embedded-signup/start")
async def owner_wa_embedded_signup_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    info = wa_embedded_signup_info()
    if not info["enabled"]:
        raise HTTPException(409, info["unavailable_reason"])
    s = get_settings()
    state = _make_wa_state(str(user["tenant_id"]))
    ver = (s.meta_graph_version or "v22.0").strip()
    redirect_uri = s.public_base_url.rstrip("/") + "/owner/social/oauth/callback"
    extras = json.dumps({"setup": {}, "featureType": "", "sessionInfoVersion": "3"}, separators=(",", ":"))
    params = urlencode({
        "client_id": s.meta_app_id.strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "config_id": s.meta_wa_embedded_signup_config_id.strip(),
        "override_default_response_type": "true",
        "extras": extras,
        "state": state,
    })
    return {
        "authorization_url": f"https://www.facebook.com/{ver}/dialog/oauth?{params}",
        "state": state,
    }


class WaEmbeddedSignupComplete(BaseModel):
    state: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=4, max_length=2048)
    waba_id: str = Field(default="", max_length=64)
    phone_number_id: str = Field(default="", max_length=64)
    display_name: str = Field(default="", max_length=200)


@owner_router.post("/whatsapp/embedded-signup/complete", status_code=201)
async def owner_wa_embedded_signup_complete(
    body: WaEmbeddedSignupComplete,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    info = wa_embedded_signup_info()
    if not info["enabled"]:
        raise HTTPException(409, info["unavailable_reason"])
    _consume_wa_state(body.state, str(user["tenant_id"]))
    s = get_settings()
    app_id = s.meta_app_id.strip()
    app_secret = s.meta_app_secret.strip()
    redirect_uri = s.public_base_url.rstrip("/") + "/owner/social/oauth/callback"

    status_code, tok_data = await _graph_request(
        "GET",
        "oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": body.code.strip(),
        },
    )
    access_token = str(tok_data.get("access_token") or "").strip()
    if status_code >= 300 or not access_token:
        raise HTTPException(400, "Meta rejected the WhatsApp Embedded Signup authorization code")

    waba_id = body.waba_id.strip()
    phone_number_id = body.phone_number_id.strip()
    display_name = body.display_name.strip()

    # If sessionInfo postMessage did not supply waba_id, discover from debug_token granular_scopes.
    if not waba_id:
        dbg_status, dbg_data = await _graph_request(
            "GET",
            "debug_token",
            params={"input_token": access_token, "access_token": f"{app_id}|{app_secret}"},
        )
        if dbg_status < 300:
            for gs in (dbg_data.get("data") or {}).get("granular_scopes") or []:
                if gs.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
                    for tid in gs.get("target_ids") or []:
                        if _DIGITS_RE.fullmatch(str(tid)):
                            waba_id = str(tid)
                            break
                if waba_id:
                    break

    if not _DIGITS_RE.fullmatch(waba_id):
        raise HTTPException(400, "Could not determine a valid WhatsApp Business Account ID (waba_id)")

    # Discover phone_number_id from WABA if not supplied by sessionInfo event.
    if not phone_number_id:
        pn_status, pn_data = await _graph_request(
            "GET",
            f"{waba_id}/phone_numbers",
            token=access_token,
            params={"fields": "id,display_phone_number,verified_name"},
        )
        if pn_status < 300:
            for entry in pn_data.get("data") or []:
                pid = str(entry.get("id") or "")
                if _DIGITS_RE.fullmatch(pid):
                    phone_number_id = pid
                    if not display_name:
                        display_name = str(
                            entry.get("verified_name") or entry.get("display_phone_number") or ""
                        ).strip()
                    break

    if not _DIGITS_RE.fullmatch(phone_number_id):
        raise HTTPException(400, "Could not determine a valid WhatsApp phone_number_id")

    # Fetch display name best-effort if still blank.
    if not display_name:
        pn_status, pn_info = await _graph_request(
            "GET",
            phone_number_id,
            token=access_token,
            params={"fields": "display_phone_number,verified_name"},
        )
        if pn_status < 300:
            display_name = str(
                pn_info.get("verified_name") or pn_info.get("display_phone_number") or ""
            ).strip()

    # Subscribe the WABA to this Meta app so inbound webhooks deliver to /webhooks/meta/messaging.
    sub_status, _ = await _graph_request("POST", f"{waba_id}/subscribed_apps", token=access_token)
    if sub_status >= 300:
        raise HTTPException(502, "Connected WhatsApp account, but Meta rejected WABA webhook subscription")

    enc = crypto_vault.encrypt_text(access_token, aad=f"meta:{user['tenant_id']}:whatsapp")
    row = await db.pool().fetchrow(
        """INSERT INTO tenant_meta_channels(
               tenant_id, channel, external_id, waba_id, display_name,
               webhook_subscribed, access_token_enc, enabled)
           VALUES($1, 'whatsapp', $2, $3, $4, true, $5, true)
           ON CONFLICT (channel, external_id) DO UPDATE SET
               waba_id=EXCLUDED.waba_id,
               display_name=EXCLUDED.display_name,
               webhook_subscribed=true,
               access_token_enc=EXCLUDED.access_token_enc,
               enabled=true
           WHERE tenant_meta_channels.tenant_id=$1
           RETURNING id, channel, external_id, waba_id, display_name, webhook_subscribed, enabled, created_at""",
        user["tenant_id"], phone_number_id, waba_id, display_name[:200], enc,
    )
    if not row:
        raise HTTPException(409, "That WhatsApp phone number is already bound to another workspace")
    return {**dict(row), "id": str(row["id"]), "created_at": row["created_at"].isoformat()}


# ---- Studio Inbox conversations & outbound replies ------------------------------------------
def _window_state(last_inbound_at: datetime | None) -> tuple[bool, str | None]:
    if not last_inbound_at:
        return False, None
    ts = last_inbound_at if last_inbound_at.tzinfo else last_inbound_at.replace(tzinfo=timezone.utc)
    expires = ts + timedelta(hours=WINDOW_HOURS)
    return datetime.now(timezone.utc) <= expires, expires.isoformat()


@owner_router.get("/conversations")
async def owner_meta_conversations(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        """SELECT channel, sender_id,
                  MAX(sender_name) FILTER (WHERE sender_name <> '') AS sender_name,
                  MAX(channel_external_id) FILTER (WHERE channel_external_id <> '') AS channel_external_id,
                  MAX(created_at) AS last_at,
                  MAX(created_at) FILTER (WHERE direction='in') AS last_inbound_at,
                  COUNT(*) AS message_count,
                  (ARRAY_AGG(text ORDER BY created_at DESC))[1] AS last_text,
                  (ARRAY_AGG(direction ORDER BY created_at DESC))[1] AS last_direction
           FROM meta_inbound_messages
           WHERE tenant_id=$1
           GROUP BY channel, sender_id
           ORDER BY last_at DESC
           LIMIT 100""",
        user["tenant_id"],
    )
    conversations = []
    for r in rows:
        win_open, win_exp = _window_state(r["last_inbound_at"])
        conversations.append({
            "channel": r["channel"],
            "sender_id": r["sender_id"],
            "sender_name": r["sender_name"] or "",
            "channel_external_id": r["channel_external_id"] or "",
            "last_text": r["last_text"] or "",
            "last_direction": r["last_direction"] or "in",
            "last_at": r["last_at"].isoformat() if r["last_at"] else "",
            "last_inbound_at": r["last_inbound_at"].isoformat() if r["last_inbound_at"] else None,
            "window_open": win_open,
            "window_expires_at": win_exp,
            "message_count": int(r["message_count"]),
        })
    return {"conversations": conversations}


@owner_router.get("/conversations/{channel}/{sender_id}")
async def owner_meta_conversation_thread(
    channel: Literal["whatsapp", "messenger", "instagram"],
    sender_id: str,
    user: dict = Depends(owner_auth.current_user),
):
    rows = await db.pool().fetch(
        """SELECT id, channel, channel_external_id, sender_id, sender_name,
                  text, template_name, direction, created_at
           FROM meta_inbound_messages
           WHERE tenant_id=$1 AND channel=$2 AND sender_id=$3
           ORDER BY created_at ASC
           LIMIT 200""",
        user["tenant_id"], channel, sender_id,
    )
    if not rows:
        raise HTTPException(404, "Conversation not found")
    last_in = max((r["created_at"] for r in rows if r["direction"] == "in"), default=None)
    win_open, win_exp = _window_state(last_in)
    sender_name = next((r["sender_name"] for r in reversed(rows) if r["sender_name"]), "")
    channel_ext = next((r["channel_external_id"] for r in reversed(rows) if r["channel_external_id"]), "")
    return {
        "channel": channel,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "channel_external_id": channel_ext,
        "window_open": win_open,
        "window_expires_at": win_exp,
        "messages": [
            {
                "id": str(r["id"]),
                "direction": r["direction"],
                "text": r["text"],
                "template_name": r["template_name"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


@owner_router.get("/whatsapp/templates")
async def owner_wa_templates(user: dict = Depends(owner_auth.current_user)):
    if not is_enabled():
        return {"templates": [], "note": "Meta messaging is disabled on this server"}
    ch_row = await db.pool().fetchrow(
        """SELECT waba_id, access_token_enc FROM tenant_meta_channels
           WHERE tenant_id=$1 AND channel='whatsapp' AND enabled AND waba_id <> ''
           ORDER BY created_at DESC LIMIT 1""",
        user["tenant_id"],
    )
    if not ch_row:
        return {"templates": [], "note": "No WhatsApp Business Account connected"}
    try:
        token = crypto_vault.decrypt_text(ch_row["access_token_enc"], aad=f"meta:{user['tenant_id']}:whatsapp")
    except ValueError:
        return {"templates": [], "note": "WhatsApp credentials need reconnection"}
    status_code, data = await _graph_request(
        "GET",
        f"{ch_row['waba_id']}/message_templates",
        token=token,
        params={"status": "APPROVED", "fields": "name,language,category,status", "limit": "50"},
    )
    if status_code >= 300:
        return {"templates": [], "note": "Could not load approved WhatsApp templates from Meta"}
    templates = [
        {
            "name": str(t.get("name") or ""),
            "language": str(t.get("language") or "en"),
            "category": str(t.get("category") or ""),
        }
        for t in (data.get("data") or [])
        if t.get("name")
    ]
    return {"templates": templates}


class MetaReplyBody(BaseModel):
    text: str = Field(default="", max_length=4000)
    template_name: str = Field(default="", max_length=512)
    template_language: str = Field(default="en", max_length=16)


@owner_router.post("/conversations/{channel}/{sender_id}/reply")
async def owner_meta_reply(
    channel: Literal["whatsapp", "messenger", "instagram"],
    sender_id: str,
    body: MetaReplyBody,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "editor")
    if not is_enabled():
        raise HTTPException(409, "Meta messaging is disabled on this server")

    text = body.text.strip()
    template_name = body.template_name.strip()
    template_lang = (body.template_language or "en").strip()
    if not text and not template_name:
        raise HTTPException(400, "Reply text or WhatsApp template_name is required")
    if template_name and (channel != "whatsapp" or not _TEMPLATE_NAME_RE.fullmatch(template_name)):
        raise HTTPException(400, "Invalid WhatsApp template name")
    if template_name and not _LANG_CODE_RE.fullmatch(template_lang):
        raise HTTPException(400, "Invalid WhatsApp template language code")

    last_in = await db.pool().fetchrow(
        """SELECT created_at, channel_external_id
           FROM meta_inbound_messages
           WHERE tenant_id=$1 AND channel=$2 AND sender_id=$3 AND direction='in'
           ORDER BY created_at DESC LIMIT 1""",
        user["tenant_id"], channel, sender_id,
    )
    win_open, _ = _window_state(last_in["created_at"] if last_in else None)
    if not win_open:
        if channel != "whatsapp":
            raise HTTPException(
                409,
                "Meta's 24-hour customer messaging window has closed for this conversation. "
                "You can reply once the customer messages you again.",
            )
        if not template_name:
            raise HTTPException(
                409,
                "WhatsApp's 24-hour customer service window has closed. "
                "Send an approved WhatsApp message template or wait for the customer to message again.",
            )

    preferred_ext = (last_in["channel_external_id"] if last_in else "") or ""
    ch_row = None
    if preferred_ext:
        ch_row = await db.pool().fetchrow(
            """SELECT id, external_id, page_id, waba_id, access_token_enc
               FROM tenant_meta_channels
               WHERE tenant_id=$1 AND channel=$2 AND external_id=$3 AND enabled""",
            user["tenant_id"], channel, preferred_ext,
        )
    if not ch_row:
        ch_row = await db.pool().fetchrow(
            """SELECT id, external_id, page_id, waba_id, access_token_enc
               FROM tenant_meta_channels
               WHERE tenant_id=$1 AND channel=$2 AND enabled
               ORDER BY created_at DESC LIMIT 1""",
            user["tenant_id"], channel,
        )
    if not ch_row:
        raise HTTPException(404, f"No connected {channel} channel found for this workspace")

    try:
        token = crypto_vault.decrypt_text(ch_row["access_token_enc"], aad=f"meta:{user['tenant_id']}:{channel}")
    except ValueError:
        raise HTTPException(500, "Stored Meta channel credentials could not be decrypted") from None

    if channel == "whatsapp":
        if template_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": sender_id,
                "type": "template",
                "template": {"name": template_name, "language": {"code": template_lang}},
            }
            stored_text = text or f"[Template: {template_name}]"
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": sender_id,
                "type": "text",
                "text": {"body": text},
            }
            stored_text = text
        status_code, resp = await _graph_request(
            "POST", f"{ch_row['external_id']}/messages", token=token, json_body=payload,
        )
        ext_mid = str(((resp.get("messages") or [{}])[0] or {}).get("id") or "")
    elif channel == "messenger":
        page_target = ch_row["page_id"] or ch_row["external_id"]
        payload = {
            "recipient": {"id": sender_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        }
        stored_text = text
        status_code, resp = await _graph_request(
            "POST", f"{page_target}/messages", token=token, json_body=payload,
        )
        ext_mid = str(resp.get("message_id") or "")
    else:  # instagram
        payload = {
            "recipient": {"id": sender_id},
            "message": {"text": text},
        }
        stored_text = text
        status_code, resp = await _graph_request(
            "POST", f"{ch_row['external_id']}/messages", token=token, json_body=payload,
        )
        ext_mid = str(resp.get("message_id") or "")

    if status_code >= 300:
        err_msg = str(((resp.get("error") or {}).get("message")) or "Meta rejected the outbound reply")
        raise HTTPException(502, err_msg[:300])

    if not ext_mid:
        ext_mid = f"out:{channel}:{secrets.token_hex(12)}"

    row = await db.pool().fetchrow(
        """INSERT INTO meta_inbound_messages(
               tenant_id, channel, channel_external_id, external_message_id,
               sender_id, sender_name, text, template_name, direction)
           VALUES($1, $2, $3, $4, $5, '', $6, $7, 'out')
           RETURNING id, created_at""",
        user["tenant_id"], channel, ch_row["external_id"], ext_mid,
        sender_id, stored_text, template_name,
    )
    return {
        "ok": True,
        "id": str(row["id"]),
        "channel": channel,
        "external_message_id": ext_mid,
        "direction": "out",
        "created_at": row["created_at"].isoformat(),
    }
