"""Owner SMS inbox: read text conversations, take over from the assistant, reply, hand back.

Texts already land in `conversations` (channel 'sms', session 'sms<digits>') and `messages`. The
owner's own replies are stored as role 'assistant' with flag 'owner', so the CRM transcript shows
them too, and they are sent through the same `sms.send_sms` path as every other text (including
the paired-phone device route). Taking over uses the existing per-customer case switch, which
already stops the assistant on every channel.
"""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import casetimeline, channel_authorization, convo, db, device_sms, outbox, owner_auth, sms, tenants

router = APIRouter(prefix="/owner/sms")
ONLINE_SECONDS = 300


def phone_of(session_id: str) -> str:
    digits = re.sub(r"\D", "", session_id or "")
    return "+" + digits if 7 <= len(digits) <= 15 else ""


def author_of(role: str, flag: str | None) -> str:
    if role == "user":
        return "customer"
    return "owner" if flag == "owner" else "ai"


async def phone_status(tenant_id) -> dict:
    device = await db.pool().fetchrow(
        "SELECT last_seen,inbound_verified_at FROM sms_devices WHERE tenant_id=$1 AND enabled", tenant_id)
    tenant = await tenants.get_by_id(tenant_id)
    transport = (tenant or {}).get("sms_transport") or ("device" if device else sms.provider())
    if not device:
        return {"transport": transport, "paired": False, "online": transport not in ("device", "none", ""),
                "last_seen": None, "receive_verified": None}
    last = device["last_seen"]
    online = bool(last and (datetime.now(timezone.utc) - last).total_seconds() < ONLINE_SECONDS)
    return {"transport": "device", "paired": True, "online": online, "last_seen": last,
            "receive_verified": bool(device["inbound_verified_at"])}


async def _paused(tenant: dict, phone: str) -> bool:
    try:
        return await casetimeline.is_paused_for(
            tenant["id"], phone=phone, default_cc=casetimeline.tenant_country_code(tenant))
    except Exception:  # noqa: BLE001 - a lookup failure must not break the inbox
        return False


async def _conversation(user: dict, conversation_id: uuid.UUID) -> dict:
    row = await db.pool().fetchrow(
        "SELECT id,session_id,started_at FROM conversations WHERE tenant_id=$1 AND id=$2 AND channel='sms'",
        user["tenant_id"], conversation_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    return dict(row)


@router.get("/inbox")
async def inbox(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "viewer")
    tenant = await tenants.get_by_id(user["tenant_id"])
    rows = await db.pool().fetch(
        """SELECT c.id, c.session_id, c.started_at, last.role, last.flag, last.content, last.created_at AS last_at,
                  (SELECT count(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count,
                  l.id AS lead_id, COALESCE(NULLIF(l.name,''), cc.display_name, '') AS name,
                  COALESCE(cc.automation_paused, false) AS paused
           FROM conversations c
           LEFT JOIN LATERAL (SELECT role,flag,content,created_at FROM messages m
                              WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) last ON true
           LEFT JOIN LATERAL (SELECT id,name,case_id FROM leads WHERE tenant_id=c.tenant_id
                              AND conversation_id=c.id ORDER BY created_at DESC LIMIT 1) l ON true
           LEFT JOIN customer_cases cc ON cc.id=l.case_id AND cc.tenant_id=c.tenant_id
           WHERE c.tenant_id=$1 AND c.channel='sms'
           ORDER BY COALESCE(last.created_at, c.started_at) DESC LIMIT 200""", user["tenant_id"])
    conversations = []
    for r in rows:
        phone = phone_of(r["session_id"])
        conversations.append({
            "id": str(r["id"]), "phone": phone, "name": r["name"] or "",
            "lead_id": str(r["lead_id"]) if r["lead_id"] else None,
            "last_text": (r["content"] or "")[:160], "last_author": author_of(r["role"] or "user", r["flag"]),
            "last_at": r["last_at"] or r["started_at"], "message_count": r["message_count"],
            "paused": bool(r["paused"]) or (await _paused(tenant, phone) if phone and not r["lead_id"] else False),
        })
    return {"phone": await phone_status(user["tenant_id"]), "conversations": conversations}


@router.get("/conversations/{conversation_id}")
async def thread(conversation_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "viewer")
    tenant = await tenants.get_by_id(user["tenant_id"])
    conv = await _conversation(user, conversation_id)
    rows = await db.pool().fetch(
        "SELECT id,role,flag,content,created_at FROM messages WHERE conversation_id=$1 "
        "AND role IN ('user','assistant') ORDER BY id LIMIT 1000", conversation_id)
    phone = phone_of(conv["session_id"])
    return {"id": str(conversation_id), "phone": phone, "paused": await _paused(tenant, phone),
            "opted_out": await outbox.is_opted_out(tenant["id"], phone) if phone else False,
            "messages": [{"id": r["id"], "author": author_of(r["role"], r["flag"]),
                          "text": r["content"], "at": r["created_at"]} for r in rows]}


class Takeover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paused: bool


async def _set_takeover(user: dict, tenant: dict, phone: str, paused: bool) -> bool:
    cc = casetimeline.tenant_country_code(tenant)
    case = await casetimeline.ensure_case(tenant["id"], phone=phone, default_cc=cc, source="owner_inbox")
    if not case:
        raise HTTPException(409, "This conversation has no usable phone number")
    return await casetimeline.set_takeover(
        tenant["id"], case_key=case["case_key"], paused=paused,
        by=str(user.get("email") or user.get("id") or "owner") + ": SMS inbox")


@router.post("/conversations/{conversation_id}/takeover")
async def takeover(conversation_id: uuid.UUID, body: Takeover, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "viewer")
    tenant = await tenants.get_by_id(user["tenant_id"])
    conv = await _conversation(user, conversation_id)
    await _set_takeover(user, tenant, phone_of(conv["session_id"]), body.paused)
    return {"paused": body.paused}


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1500)
    request_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


@router.post("/conversations/{conversation_id}/reply")
async def reply(conversation_id: uuid.UUID, body: Reply, user: dict = Depends(owner_auth.current_user)):
    """Send the owner's own text. Replying takes the customer over, so the assistant stops talking."""
    owner_auth.require_role(user, "editor")
    tenant = await tenants.get_by_id(user["tenant_id"])
    conv = await _conversation(user, conversation_id)
    phone = phone_of(conv["session_id"])
    text = body.text.strip()
    if not phone or not text:
        raise HTTPException(422, "Nothing to send")
    if await outbox.is_opted_out(tenant["id"], phone):
        raise HTTPException(409, "This person replied STOP, so they cannot be texted")
    if not await channel_authorization.is_authorized(tenant["id"], "sms_send"):
        raise HTTPException(409, "Texting customers is not switched on in Permissions")
    await _set_takeover(user, tenant, phone, True)
    status = "sent"
    try:
        await sms.send_sms(phone, text, tenant.get("sms_from"), tenant=tenant,
                           request_key="owner-reply:" + body.request_id)
    except device_sms.AwaitingReceipt:
        status = "queued"  # the paired phone picks it up within seconds
    except device_sms.ReconciliationRequired:
        raise HTTPException(409, "An earlier text to this person needs checking before another is sent") from None
    except sms.SmsRateLimited as error:
        raise HTTPException(429, str(error)) from None
    except (sms.SmsNotConfigured, ValueError) as error:
        raise HTTPException(409, str(error)) from None
    await convo.save_message(conversation_id, "assistant", text, "owner")
    return {"status": status, "paused": True}
