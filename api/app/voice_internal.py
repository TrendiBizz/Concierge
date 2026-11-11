"""Loopback API for the Rust telephone shell.

The shell owns sockets, audio and Grok; this API owns the database, permissions,
recordings, CRM and tools, so those rules stay in one place. It is never routed
publicly: the shell calls http://api:8000 on the private compose network and must
present the shared internal token.
"""
import base64
import hmac

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import asterisk_bridge, channel_authorization, db, tenants, voice_records
from .config import get_settings

router = APIRouter(prefix="/internal/voice", include_in_schema=False)


def _authorize(token: str | None) -> None:
    expected = get_settings().internal_token
    if not expected:
        raise HTTPException(503, "Internal voice API is disabled")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Unauthorized")


class Start(BaseModel):
    slug: str = Field(max_length=80)
    number: str = Field(max_length=20)
    call_id: str = Field(max_length=120)


class Transcript(BaseModel):
    conversation_id: str
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=10000)
    item_id: str | None = Field(default=None, max_length=200)


class Tool(BaseModel):
    tenant_id: str
    record_session_id: str
    conversation_id: str
    call_id: str = Field(max_length=120)
    name: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)


class Monitor(BaseModel):
    tenant_id: str
    record_session_id: str


class Finish(BaseModel):
    tenant_id: str
    call_id: str = Field(max_length=120)
    conversation_id: str
    status: str = Field(max_length=40)
    record_session_id: str | None = None


class Recording(BaseModel):
    record_session_id: str
    wav_b64: str


@router.post("/start")
async def start(body: Start, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    route = asterisk_bridge.Route(body.slug, body.number, 0)
    try:
        prepared = await asterisk_bridge.prepare(route, body.call_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {
        "tenant": prepared["tenant"],
        "conversation_id": prepared["conversation"],
        "record_session": prepared["record_session"],
        "session": prepared["session"],
    }


@router.post("/transcript")
async def transcript(body: Transcript, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    if body.item_id:
        row = await db.pool().fetchrow(
            """INSERT INTO messages(conversation_id,role,content,item_id)
               VALUES($1,$2,$3,$4)
               ON CONFLICT (conversation_id,item_id) WHERE item_id IS NOT NULL
               DO UPDATE SET content=EXCLUDED.content
               RETURNING id""",
            body.conversation_id, body.role, body.text, body.item_id)
    else:
        row = await db.pool().fetchrow(
            "INSERT INTO messages(conversation_id,role,content) VALUES($1,$2,$3) RETURNING id",
            body.conversation_id, body.role, body.text)
    return {"id": row["id"]}


@router.post("/tool")
async def tool(body: Tool, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    tenant = await tenants.get_by_id(body.tenant_id)
    if not tenant:
        raise HTTPException(404, "Unknown business")
    record = await db.pool().fetchrow(
        "SELECT * FROM voice_sessions WHERE id=$1 AND tenant_id=$2",
        body.record_session_id, body.tenant_id)
    if not record:
        raise HTTPException(404, "Unknown voice session")
    try:
        return await asterisk_bridge.run_phone_tool(
            tenant, dict(record), body.conversation_id, body.call_id,
            body.name, body.args, None)
    except ValueError as exc:
        raise HTTPException(403, str(exc))


@router.post("/monitor")
async def monitor(body: Monitor, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    return {
        "telephone": await channel_authorization.is_authorized(body.tenant_id, "telephone"),
        "recording": await channel_authorization.is_authorized(body.tenant_id, "call_recording"),
    }


@router.post("/finish")
async def finish(body: Finish, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    tenant = await tenants.get_by_id(body.tenant_id)
    if not tenant:
        raise HTTPException(404, "Unknown business")
    record = None
    if body.record_session_id:
        record = await db.pool().fetchrow(
            "SELECT * FROM voice_sessions WHERE id=$1 AND tenant_id=$2",
            body.record_session_id, body.tenant_id)
        record = dict(record) if record else None
    await asterisk_bridge.finish(tenant, body.call_id, body.conversation_id, body.status, record)
    if record:
        request = await db.pool().fetchval(
            "UPDATE voice_sessions SET finalized_at=now() WHERE id=$1 AND finalized_at IS NULL "
            "RETURNING delivery_request", body.record_session_id)
        if request is not None:
            await voice_records.complete_delivery(record, tenant, request, {"ok": True})
    return {"ok": True}


@router.post("/recording")
async def recording(body: Recording, x_concierge_internal: str | None = Header(default=None)):
    _authorize(x_concierge_internal)
    try:
        raw = base64.b64decode(body.wav_b64, validate=True)
    except ValueError:
        raise HTTPException(400, "Invalid audio")
    record = await db.pool().fetchrow("SELECT * FROM voice_sessions WHERE id=$1", body.record_session_id)
    if not record:
        raise HTTPException(404, "Unknown voice session")
    tenant = await tenants.get_by_id(record["tenant_id"])
    if not tenant:
        raise HTTPException(404, "Unknown business")
    record = dict(record)
    await voice_records.store_audio(record, raw, "audio/wav")
    request = await db.pool().fetchval(
        "UPDATE voice_sessions SET finalized_at=now() WHERE id=$1 RETURNING delivery_request",
        body.record_session_id)
    await voice_records.complete_delivery(record, tenant, request, {"ok": True})
    return {"ok": True}
