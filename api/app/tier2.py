"""Tier 2 Features (H1, H2, H3, H5, H6, H8, H10, H11; H7 deliberately skipped):
- H1: Visitor photo/file upload in web chat & MMS (/api/v1/chat/upload + /owner/chat-uploads/{id})
- H2: Google Business Profile review inbox & AI drafted replies (posting off until GBP_REVIEWS_ENABLED)
- H3: Multi-staff / resource scheduling & buffer times (/owner/staff)
- H5: Custom CRM pipeline stages & contact tags (/owner/crm/stages, /owner/contacts/{case_id}/tags)
- H6: Owner Slack/Teams webhook config endpoint (/owner/team-chat-webhook)
- H8: Real-time Studio Server-Sent Events (/owner/events/stream)
- H10: Outbound AI confirmation/follow-up calls (OFF by default, owner-initiated only)
- H11: Partner / multi-location RBAC (/admin/partners + /partner/tenants)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import db, owner_auth, public_fetch
from .config import get_settings
from .security import require_admin

owner_router = APIRouter(prefix="/owner", tags=["tier2"])
public_router = APIRouter(prefix="/api/v1", tags=["tier2"])
admin_router = APIRouter(prefix="/admin", tags=["tier2-partners"])
partner_router = APIRouter(prefix="/partner", tags=["tier2-partners"])

MAX_CHAT_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

# ---- H8: In-process per-tenant SSE event bus ------------------------------------------------
_SSE_SUBSCRIBERS: dict[str, set[asyncio.Queue]] = defaultdict(set)


def publish_event(tenant_id, event_type: str, payload: dict) -> None:
    """Publish a real-time event to all connected Studio SSE clients for this tenant."""
    tid = str(tenant_id)
    frame = {"type": event_type, "data": payload}
    for q in list(_SSE_SUBSCRIBERS.get(tid, ())):
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass


@owner_router.get("/events/stream")
async def owner_sse_stream(
    once: bool = Query(default=False),
    user: dict = Depends(owner_auth.current_user),
):
    tid = str(user["tenant_id"])
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _SSE_SUBSCRIBERS[tid].add(q)

    async def gen():
        try:
            yield f"event: connected\ndata: {json.dumps({'tenant_id': tid})}\n\n"
            if once:
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"event: {ev['type']}\ndata: {json.dumps(ev['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _SSE_SUBSCRIBERS[tid].discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---- H6: Studio field for Slack / Microsoft Teams webhook -----------------------------------
class TeamChatWebhookBody(BaseModel):
    url: str = Field(default="", max_length=1000)


@owner_router.get("/team-chat-webhook")
async def get_team_chat_webhook(user: dict = Depends(owner_auth.current_user)):
    url = await db.pool().fetchval("SELECT team_chat_webhook_url FROM tenants WHERE id=$1", user["tenant_id"])
    return {"url": url or ""}


@owner_router.put("/team-chat-webhook")
async def set_team_chat_webhook(body: TeamChatWebhookBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    clean = body.url.strip()
    if clean:
        try:
            public_fetch.validate_public_https_url(clean)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    await db.pool().execute(
        "UPDATE tenants SET team_chat_webhook_url=$2 WHERE id=$1", user["tenant_id"], clean
    )
    return {"url": clean}


# ---- H1: Visitor photo/file upload in web chat & MMS ----------------------------------------
@public_router.post("/chat/upload", status_code=201)
async def public_chat_upload(request: Request):
    """Accept a visitor photo/PDF upload (JSON base64 or raw bytes with X-Public-Key header)."""
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        body = await request.json()
        key = str(body.get("key") or "").strip()
        session_id = str(body.get("session_id") or "").strip()[:128]
        filename = str(body.get("filename") or "photo.jpg").strip()
        mime = str(body.get("content_type") or "image/jpeg").strip().lower()
        try:
            data = base64.b64decode(str(body.get("content_base64") or ""), validate=True)
        except Exception:
            raise HTTPException(400, "Invalid base64 payload") from None
    else:
        key = (request.headers.get("x-public-key") or "").strip()
        session_id = (request.headers.get("x-session-id") or "").strip()[:128]
        filename = (request.headers.get("x-filename") or "photo.jpg").strip()
        mime = ctype.split(";", 1)[0].strip() or "application/octet-stream"
        data = await request.body()

    if not key:
        raise HTTPException(400, "Missing business public key")
    tenant_id = await db.pool().fetchval("SELECT id FROM tenants WHERE public_key=$1", key)
    if not tenant_id:
        raise HTTPException(404, "Unknown business key")
    if mime not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(400, "Allowed file types: JPEG, PNG, WebP, PDF")
    if not data or len(data) > MAX_CHAT_UPLOAD_BYTES:
        raise HTTPException(413, "File must be between 1 byte and 5 MB")

    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", filename)[:200] or "upload.bin"
    digest = hashlib.sha256(data).hexdigest()
    row = await db.pool().fetchrow(
        "INSERT INTO chat_uploads(tenant_id, session_id, filename, content_type, size_bytes, sha256, data) "
        "VALUES($1, $2, $3, $4, $5, $6, $7) RETURNING id, created_at",
        tenant_id, session_id, safe_name, mime, len(data), digest, data,
    )
    publish_event(tenant_id, "chat.upload", {"id": str(row["id"]), "filename": safe_name, "session_id": session_id})
    return {"id": str(row["id"]), "filename": safe_name, "content_type": mime, "size_bytes": len(data)}


@owner_router.get("/chat-uploads/{upload_id}")
async def owner_get_chat_upload(upload_id: str, user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT filename, content_type, data FROM chat_uploads WHERE id=$1 AND tenant_id=$2",
        upload_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Upload not found")
    return Response(
        content=bytes(row["data"]),
        media_type=row["content_type"],
        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"', "X-Content-Type-Options": "nosniff"},
    )


# ---- H2: Google Business Profile review monitoring & AI drafted replies ---------------------
@owner_router.get("/reviews")
async def list_gbp_reviews(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, external_review_id, reviewer_name, rating, comment, ai_draft_reply, reply_status, replied_at, created_at "
        "FROM gbp_reviews WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 100",
        user["tenant_id"],
    )
    return {
        "gbp_live_posting_enabled": bool(get_settings().gbp_reviews_enabled),
        "reviews": [
            {**dict(r), "id": str(r["id"]),
             "replied_at": r["replied_at"].isoformat() if r["replied_at"] else None,
             "created_at": r["created_at"].isoformat()}
            for r in rows
        ],
    }


@owner_router.post("/reviews/{review_id}/draft-reply")
async def draft_review_reply(review_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "SELECT id, reviewer_name, rating, comment FROM gbp_reviews WHERE id=$1 AND tenant_id=$2",
        review_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Review not found")
    who = (row["reviewer_name"] or "there").strip()
    if int(row["rating"]) >= 4:
        draft = f"Thank you so much for the {row['rating']}-star review, {who}! We really appreciate your feedback and look forward to helping you again."
    else:
        draft = f"Thank you for letting us know, {who}. We take feedback seriously and would love to make this right — please reach out to our team directly."
    await db.pool().execute(
        "UPDATE gbp_reviews SET ai_draft_reply=$2 WHERE id=$1", row["id"], draft
    )
    return {"id": str(row["id"]), "ai_draft_reply": draft}


@owner_router.post("/reviews/{review_id}/approve")
async def approve_review_reply(review_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "UPDATE gbp_reviews SET reply_status='approved', replied_at=now() "
        "WHERE id=$1 AND tenant_id=$2 RETURNING id, reply_status",
        review_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Review not found")
    return {"id": str(row["id"]), "reply_status": row["reply_status"], "live_posted": False}


# ---- H3: Multi-staff / resource scheduling & buffer times -----------------------------------
class StaffCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(default="", max_length=320)
    service_types: list[str] = Field(default_factory=list)
    slot_minutes: int = Field(default=30, ge=10, le=240)
    buffer_minutes: int = Field(default=10, ge=0, le=120)


@owner_router.get("/staff")
async def list_staff(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, name, email, service_types, slot_minutes, buffer_minutes, active, created_at "
        "FROM staff_resources WHERE tenant_id=$1 ORDER BY name ASC",
        user["tenant_id"],
    )
    return [
        {**dict(r), "id": str(r["id"]),
         "service_types": json.loads(r["service_types"]) if isinstance(r["service_types"], str) else list(r["service_types"] or []),
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@owner_router.post("/staff", status_code=201)
async def create_staff(body: StaffCreate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "INSERT INTO staff_resources(tenant_id, name, email, service_types, slot_minutes, buffer_minutes) "
        "VALUES($1, $2, $3, $4::jsonb, $5, $6) RETURNING id, created_at",
        user["tenant_id"], body.name.strip(), body.email.strip().lower(),
        json.dumps([s.strip()[:60] for s in body.service_types if s.strip()]),
        body.slot_minutes, body.buffer_minutes,
    )
    return {"id": str(row["id"]), "name": body.name.strip(), "slot_minutes": body.slot_minutes, "buffer_minutes": body.buffer_minutes}


@owner_router.delete("/staff/{staff_id}")
async def delete_staff(staff_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    res = await db.pool().execute(
        "DELETE FROM staff_resources WHERE id=$1 AND tenant_id=$2", staff_id, user["tenant_id"]
    )
    if res.endswith("0"):
        raise HTTPException(404, "Staff member not found")
    return {"ok": True}


# ---- H5: Custom CRM pipeline stages & contact tags ------------------------------------------
class StageItem(BaseModel):
    slug: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=60)
    colour: str = Field(default="#6366f1", max_length=20)


class StagesUpdate(BaseModel):
    stages: list[StageItem] = Field(min_length=1, max_length=15)


@owner_router.get("/crm/stages")
async def get_crm_stages(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT slug, label, position, colour FROM tenant_crm_stages WHERE tenant_id=$1 ORDER BY position ASC",
        user["tenant_id"],
    )
    if not rows:
        return {"stages": [
            {"slug": "new", "label": "New", "position": 0, "colour": "#3b82f6"},
            {"slug": "contacted", "label": "Contacted", "position": 1, "colour": "#8b5cf6"},
            {"slug": "booked", "label": "Booked", "position": 2, "colour": "#f59e0b"},
            {"slug": "won", "label": "Won", "position": 3, "colour": "#10b981"},
            {"slug": "lost", "label": "Lost", "position": 4, "colour": "#6b7280"},
        ]}
    return {"stages": [dict(r) for r in rows]}


@owner_router.put("/crm/stages")
async def set_crm_stages(body: StagesUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM tenant_crm_stages WHERE tenant_id=$1", user["tenant_id"])
            for pos, st in enumerate(body.stages):
                await conn.execute(
                    "INSERT INTO tenant_crm_stages(tenant_id, slug, label, position, colour) VALUES($1, $2, $3, $4, $5)",
                    user["tenant_id"], st.slug, st.label.strip(), pos, st.colour.strip(),
                )
    return {"stages": [s.model_dump() for s in body.stages]}


class TagBody(BaseModel):
    tag: str = Field(min_length=1, max_length=40)


@owner_router.get("/contacts/{case_id}/tags")
async def get_contact_tags(case_id: str, user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT tag, created_at FROM contact_tags WHERE tenant_id=$1 AND case_id=$2 ORDER BY tag ASC",
        user["tenant_id"], case_id,
    )
    return {"tags": [r["tag"] for r in rows]}


@owner_router.post("/contacts/{case_id}/tags", status_code=201)
async def add_contact_tag(case_id: str, body: TagBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    tag = body.tag.strip().lower()[:40]
    await db.pool().execute(
        "INSERT INTO contact_tags(tenant_id, case_id, tag) VALUES($1, $2, $3) ON CONFLICT DO NOTHING",
        user["tenant_id"], case_id, tag,
    )
    return {"tag": tag}


@owner_router.delete("/contacts/{case_id}/tags/{tag}")
async def remove_contact_tag(case_id: str, tag: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    await db.pool().execute(
        "DELETE FROM contact_tags WHERE tenant_id=$1 AND case_id=$2 AND tag=$3",
        user["tenant_id"], case_id, tag.strip().lower(),
    )
    return {"ok": True}


# ---- H10: Outbound AI calls (OFF by default, owner-initiated only) --------------------------
class OutboundCallBody(BaseModel):
    to_number: str = Field(min_length=6, max_length=32)
    purpose: Literal["booking_confirmation", "follow_up", "reminder"] = "booking_confirmation"
    script_notes: str = Field(default="", max_length=500)


@owner_router.post("/voice/outbound-calls", status_code=201)
async def initiate_outbound_ai_call(body: OutboundCallBody, user: dict = Depends(owner_auth.current_user)):
    """Owner-initiated outbound AI call. Strictly OFF by default (`OUTBOUND_AI_CALLS_ENABLED=false`)."""
    owner_auth.require_role(user, "owner")
    if not get_settings().outbound_ai_calls_enabled:
        raise HTTPException(409, "Outbound AI calls are disabled by default (set OUTBOUND_AI_CALLS_ENABLED=true to enable)")
    num = body.to_number.strip()
    if not re.fullmatch(r"\+[1-9]\d{6,14}", num):
        raise HTTPException(400, "to_number must be E.164 (e.g. +64211234567)")
    opted_out = await db.pool().fetchval(
        "SELECT 1 FROM opt_outs WHERE tenant_id=$1 AND contact=$2 LIMIT 1", user["tenant_id"], num
    )
    if opted_out:
        raise HTTPException(409, "Recipient has opted out")
    row = await db.pool().fetchrow(
        "INSERT INTO outbound_ai_calls(tenant_id, to_number, purpose, script_notes, status, initiated_by) "
        "VALUES($1, $2, $3, $4, 'queued', $5) RETURNING id, status, created_at",
        user["tenant_id"], num, body.purpose, body.script_notes.strip(), user.get("email") or "owner",
    )
    return {"id": str(row["id"]), "to_number": num, "purpose": body.purpose, "status": row["status"]}


# ---- H11: Partner / multi-location RBAC -----------------------------------------------------
class PartnerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)


class PartnerLinkBody(BaseModel):
    tenant_id: str
    role: Literal["viewer", "editor", "owner"] = "viewer"


@admin_router.post("/partners", status_code=201, dependencies=[Depends(require_admin)])
async def admin_create_partner(body: PartnerCreate):
    raw_token = "prt_" + secrets.token_urlsafe(32)
    row = await db.pool().fetchrow(
        "INSERT INTO partner_accounts(name, email, token_hash) VALUES($1, $2, $3) RETURNING id, created_at",
        body.name.strip(), body.email.strip().lower(), hashlib.sha256(raw_token.encode()).hexdigest(),
    )
    return {"id": str(row["id"]), "name": body.name.strip(), "token": raw_token}


@admin_router.post("/partners/{partner_id}/tenants", status_code=201, dependencies=[Depends(require_admin)])
async def admin_link_partner_tenant(partner_id: str, body: PartnerLinkBody):
    await db.pool().execute(
        """INSERT INTO partner_tenant_links(partner_id, tenant_id, role) VALUES($1, $2, $3)
           ON CONFLICT (partner_id, tenant_id) DO UPDATE SET role=$3""",
        partner_id, body.tenant_id, body.role,
    )
    return {"ok": True, "partner_id": partner_id, "tenant_id": body.tenant_id, "role": body.role}


async def current_partner(x_partner_token: str = Header(default="")) -> dict:
    if not x_partner_token or len(x_partner_token) > 256:
        raise HTTPException(401, "X-Partner-Token required")
    row = await db.pool().fetchrow(
        "SELECT id, name, email FROM partner_accounts WHERE token_hash=$1 AND active",
        hashlib.sha256(x_partner_token.encode()).hexdigest(),
    )
    if not row:
        raise HTTPException(401, "Invalid partner token")
    return dict(row)


@partner_router.get("/tenants")
async def partner_list_tenants(partner: dict = Depends(current_partner)):
    rows = await db.pool().fetch(
        "SELECT t.id, t.slug, t.name, l.role FROM partner_tenant_links l "
        "JOIN tenants t ON t.id = l.tenant_id WHERE l.partner_id=$1 ORDER BY t.name ASC",
        partner["id"],
    )
    return {"partner": partner["name"], "tenants": [{**dict(r), "id": str(r["id"])} for r in rows]}
