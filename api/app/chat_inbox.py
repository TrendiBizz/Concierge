"""Owner web-chat inbox: read website chats, take over, reply live, hand back.

Website visitors have no phone or email, so the takeover switch is stored on the conversation
(`conversations.owner_takeover_at`; `casetimeline.is_paused_for_session` reads it, and also still
honours the customer-case switch). The owner's reply is saved as role 'assistant', flag 'owner'.
The widget polls `/api/v1/chat/poll` and shows owner messages it has not seen yet, so the visitor
gets the human reply in place. No carrier is involved.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from . import convo, db, owner_auth, tenants

router = APIRouter()


def author_of(role: str, flag: str | None) -> str:
    if role == "user":
        return "customer"
    return "owner" if (flag or "").startswith("owner") else "ai"
POLL_LIMIT = 50


async def _conversation(user: dict, conversation_id: uuid.UUID) -> dict:
    row = await db.pool().fetchrow(
        "SELECT id,session_id,started_at,page_url,owner_takeover_at FROM conversations "
        "WHERE tenant_id=$1 AND id=$2 AND channel='chat'", user["tenant_id"], conversation_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    return dict(row)


@router.get("/owner/chat/inbox")
async def inbox(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "viewer")
    rows = await db.pool().fetch(
        """SELECT c.id, c.started_at, c.page_url, c.owner_takeover_at, last.role, last.flag, last.content,
                  last.created_at AS last_at,
                  (SELECT count(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count,
                  COALESCE(NULLIF(l.name,''), '') AS name, l.id AS lead_id
           FROM conversations c
           JOIN LATERAL (SELECT role,flag,content,created_at FROM messages m
                         WHERE m.conversation_id=c.id AND m.role IN ('user','assistant')
                         ORDER BY m.id DESC LIMIT 1) last ON true
           LEFT JOIN LATERAL (SELECT id,name FROM leads WHERE tenant_id=c.tenant_id
                              AND conversation_id=c.id ORDER BY created_at DESC LIMIT 1) l ON true
           WHERE c.tenant_id=$1 AND c.channel='chat'
           ORDER BY last.created_at DESC LIMIT 200""", user["tenant_id"])
    return {"conversations": [{
        "id": str(r["id"]), "name": r["name"], "phone": "", "lead_id": str(r["lead_id"]) if r["lead_id"] else None,
        "page_url": r["page_url"] or "", "last_text": (r["content"] or "")[:160],
        "last_author": author_of(r["role"], r["flag"]), "last_at": r["last_at"],
        "message_count": r["message_count"], "paused": r["owner_takeover_at"] is not None,
    } for r in rows]}


@router.get("/owner/chat/conversations/{conversation_id}")
async def thread(conversation_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "viewer")
    conv = await _conversation(user, conversation_id)
    rows = await db.pool().fetch(
        "SELECT id,role,flag,content,created_at FROM messages WHERE conversation_id=$1 "
        "AND role IN ('user','assistant') ORDER BY id LIMIT 1000", conversation_id)
    return {"id": str(conversation_id), "phone": "", "opted_out": False,
            "paused": conv["owner_takeover_at"] is not None,
            "messages": [{"id": r["id"], "author": author_of(r["role"], r["flag"]),
                          "text": r["content"], "at": r["created_at"]} for r in rows]}


class Takeover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paused: bool


async def _set_takeover(tenant_id, conversation_id, paused: bool) -> None:
    await db.pool().execute(
        "UPDATE conversations SET owner_takeover_at = CASE WHEN $3 THEN COALESCE(owner_takeover_at, now()) ELSE NULL END "
        "WHERE tenant_id=$1 AND id=$2", tenant_id, conversation_id, paused)


@router.post("/owner/chat/conversations/{conversation_id}/takeover")
async def takeover(conversation_id: uuid.UUID, body: Takeover, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    await _conversation(user, conversation_id)
    await _set_takeover(user["tenant_id"], conversation_id, body.paused)
    return {"paused": body.paused}


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1500)
    request_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


@router.post("/owner/chat/conversations/{conversation_id}/reply")
async def reply(conversation_id: uuid.UUID, body: Reply, user: dict = Depends(owner_auth.current_user)):
    """Save the owner's message for the visitor's widget to pick up. Replying takes over."""
    owner_auth.require_role(user, "editor")
    await _conversation(user, conversation_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Nothing to send")
    # request_id makes a double click harmless: the same id is stored once.
    marker = "owner-reply:" + body.request_id
    duplicate = await db.pool().fetchval(
        "SELECT id FROM messages WHERE conversation_id=$1 AND flag=$2", conversation_id, marker)
    if not duplicate:
        await convo.save_message(conversation_id, "assistant", text, marker)
    await _set_takeover(user["tenant_id"], conversation_id, True)
    return {"status": "sent", "paused": True}


@router.get("/api/v1/chat/poll")
async def poll(request: Request, key: str, session_id: str, after: int = 0):
    """Owner messages the visitor has not seen yet (the widget calls this while the chat is open)."""
    from . import main
    sid = convo.clean_session(session_id)
    main._poll_rate_limit(request, sid)
    tenant = await main._tenant_for(request, key)
    rows = await db.pool().fetch(
        """SELECT m.id, m.content FROM messages m JOIN conversations c ON c.id=m.conversation_id
           WHERE c.tenant_id=$1 AND c.session_id=$2 AND c.channel='chat'
             AND m.role='assistant' AND (m.flag='owner' OR m.flag LIKE 'owner-reply:%') AND m.id > $3
           ORDER BY m.id LIMIT $4""", tenant["id"], sid, max(after, 0), POLL_LIMIT)
    paused = await db.pool().fetchval(
        "SELECT owner_takeover_at IS NOT NULL FROM conversations WHERE tenant_id=$1 AND session_id=$2 AND channel='chat'",
        tenant["id"], sid)
    return {"messages": [{"id": r["id"], "text": r["content"]} for r in rows], "human": bool(paused)}
