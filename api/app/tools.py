"""Tools the AI can call. Shared by the text chat (OpenAI format) and Grok Voice (flat format).

Every tool executes server-side and is scoped to the tenant that owns the public key, so the
browser can never read another client's data.
"""

import asyncio
import json
import logging
import re

import httpx

from . import db
from .rag import retrieve, tag_url

log = logging.getLogger("concierge.tools")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TOOL_SPECS: list[dict] = [
    {
        "name": "capture_lead",
        "description": (
            "Save a visitor's contact details and what they want so the business can follow up. "
            "Only call this after the visitor has given a phone number or email."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Visitor's name"},
                "email": {"type": "string", "description": "Visitor's email, if given"},
                "phone": {"type": "string", "description": "Visitor's phone number, if given"},
                "message": {
                    "type": "string",
                    "description": "What they want: product, quantity, question, or follow-up action",
                },
            },
            "required": ["message"],
        },
        "voice": True,
        "chat": True,
    },
    {
        "name": "get_booking_link",
        "description": "Get the link where the visitor can book an appointment.",
        "parameters": {"type": "object", "properties": {}},
        "voice": True,
        "chat": True,
    },
    {
        "name": "search_knowledge",
        "description": (
            "Search the business's website content. Call this before answering any question "
            "about the business, its products, services, prices, hours or policies."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look up"}},
            "required": ["query"],
        },
        "voice": True,
        "chat": False,
    },
]


def chat_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {k: s[k] for k in ("name", "description", "parameters")},
        }
        for s in TOOL_SPECS
        if s["chat"]
    ]


def voice_tools() -> list[dict]:
    return [
        {"type": "function", **{k: s[k] for k in ("name", "description", "parameters")}}
        for s in TOOL_SPECS
        if s["voice"]
    ]


_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _send_webhook(tenant: dict, lead: dict) -> None:
    url = tenant.get("lead_webhook_url")
    if not url:
        return
    payload = {
        "event": "lead.created",
        "tenant": {"slug": tenant["slug"], "name": tenant["name"]},
        "lead": {
            "id": str(lead["id"]),
            "name": lead["name"],
            "email": lead["email"],
            "phone": lead["phone"],
            "message": lead["message"],
            "channel": lead["channel"],
            "page_url": lead["page_url"],
            "utm": json.loads(lead["utm"]) if isinstance(lead["utm"], str) else lead["utm"],
            "created_at": lead["created_at"].isoformat(),
        },
    }
    status = "failed"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            status = f"ok:{resp.status_code}" if resp.is_success else f"http:{resp.status_code}"
    except httpx.HTTPError as exc:
        log.warning("lead webhook failed for %s: %s", tenant["slug"], exc)
        status = "error"
    await db.pool().execute("UPDATE leads SET webhook_status = $2 WHERE id = $1", lead["id"], status)


async def _capture_lead(tenant: dict, args: dict, ctx: dict) -> dict:
    name = str(args.get("name") or "").strip()[:120]
    email = str(args.get("email") or "").strip()[:200]
    phone = str(args.get("phone") or "").strip()[:40]
    message = str(args.get("message") or "").strip()[:1000]

    digits = re.sub(r"\D", "", phone)
    email_ok = bool(email and EMAIL_RE.match(email))
    phone_ok = len(digits) >= 7
    if not (email_ok or phone_ok):
        return {"ok": False, "error": "Need a valid phone number or email address. Ask the visitor for one."}

    row = await db.pool().fetchrow(
        """
        INSERT INTO leads (tenant_id, conversation_id, name, email, phone, message, channel,
                           page_url, utm, webhook_status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
        RETURNING *
        """,
        tenant["id"],
        ctx.get("conversation_id"),
        name,
        email if email_ok else "",
        phone if phone_ok else "",
        message,
        ctx.get("channel", "chat"),
        ctx.get("page_url"),
        json.dumps(ctx.get("utm") or {}),
        "pending" if tenant.get("lead_webhook_url") else "none",
    )
    lead = dict(row)
    _spawn(_send_webhook(tenant, lead))
    ctx["lead_captured"] = True
    return {"ok": True, "note": "Lead saved. Tell the visitor the team will be in touch."}


async def _get_booking_link(tenant: dict, args: dict, ctx: dict) -> dict:
    if not tenant.get("booking_url"):
        return {
            "ok": False,
            "error": "No booking link is configured. Offer to take the visitor's contact details instead.",
        }
    ctx["booking_url"] = tenant["booking_url"]
    return {"ok": True, "booking_url": tag_url(tenant["booking_url"], ctx.get("channel", "chat"))}


async def _search_knowledge(tenant: dict, args: dict, ctx: dict) -> dict:
    query = str(args.get("query") or "").strip()[:300]
    if not query:
        return {"ok": False, "error": "Empty query"}
    hits = await retrieve(tenant["id"], query, k=4)
    return {
        "ok": True,
        "results": [
            {"title": h["title"], "url": h["url"], "content": h["content"][:900]} for h in hits
        ],
    }


_HANDLERS = {
    "capture_lead": _capture_lead,
    "get_booking_link": _get_booking_link,
    "search_knowledge": _search_knowledge,
}


async def run_tool(tenant: dict, name: str, args: dict, ctx: dict) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return await handler(tenant, args if isinstance(args, dict) else {}, ctx)
    except Exception:  # a tool failure must not break the conversation
        log.exception("tool %s failed", name)
        return {"ok": False, "error": "Tool failed. Apologise briefly and offer to take contact details."}
