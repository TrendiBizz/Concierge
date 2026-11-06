"""Tools the AI can call. Shared by text chat / SMS (OpenAI format) and Grok Voice (flat format).

Every tool executes server-side and is scoped to the tenant that owns the public key, so the
browser can never read another client's data. Which tools exist depends on the tenant: native
booking tools only appear when the client has turned native booking on.
"""

import json
import logging

from . import automation, booking, db
from .config import get_settings
from .contact import is_email, normalize_phone
from .rag import retrieve, tag_url

log = logging.getLogger("concierge.tools")

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
                "consent_to_contact": {
                    "type": "boolean",
                    "description": "True only if the visitor agreed to be texted or emailed by the business",
                },
                "consent_to_marketing": {
                    "type": "boolean",
                    "description": (
                        "True only if the visitor explicitly said yes when asked whether they also want "
                        "offers and promotions. Never assume it, and never set it just because they gave contact details."
                    ),
                },
            },
            "required": ["message"],
        },
        "voice": True,
        "chat": True,
        "available": lambda t: True,
    },
    {
        "name": "get_booking_link",
        "description": "Get the link where the visitor can book an appointment.",
        "parameters": {"type": "object", "properties": {}},
        "voice": True,
        "chat": True,
        "available": lambda t: bool(t.get("booking_url")) and not t.get("native_booking"),
    },
    {
        "name": "check_availability",
        "description": (
            "List free appointment times for one date (business local time). Never offer a time "
            "that this tool did not return."
        ),
        "parameters": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date"],
        },
        "voice": True,
        "chat": True,
        "available": lambda t: bool(t.get("native_booking")),
    },
    {
        "name": "book_appointment",
        "description": (
            "Book an appointment. The first call returns a read-back sentence: read it to the "
            "visitor and wait for a clear yes, then call again with the same start and name and "
            "confirmed=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Local start time, e.g. 2026-11-05 14:30"},
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "notes": {"type": "string", "description": "What the visit is for"},
                "consent_to_contact": {
                    "type": "boolean",
                    "description": "True only if the visitor agreed to reminders by text or email",
                },
                "confirmed": {"type": "boolean", "description": "True only after the visitor said yes to the read-back"},
            },
            "required": ["start", "name"],
        },
        "voice": True,
        "chat": True,
        "available": lambda t: bool(t.get("native_booking")),
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
        "available": lambda t: True,
    },
]


def chat_tools(tenant: dict) -> list[dict]:
    return [
        {"type": "function", "function": {k: s[k] for k in ("name", "description", "parameters")}}
        for s in TOOL_SPECS
        if s["chat"] and s["available"](tenant)
    ]


def voice_tools(tenant: dict) -> list[dict]:
    return [
        {"type": "function", **{k: s[k] for k in ("name", "description", "parameters")}}
        for s in TOOL_SPECS
        if s["voice"] and s["available"](tenant)
    ]


async def _capture_lead(tenant: dict, args: dict, ctx: dict) -> dict:
    settings = get_settings()
    name = str(args.get("name") or "").strip()[:120]
    email = str(args.get("email") or "").strip()[:200]
    phone_raw = str(args.get("phone") or ctx.get("sender_phone") or "").strip()[:40]
    message = str(args.get("message") or "").strip()[:1000]
    consent = bool(args.get("consent_to_contact")) or bool(ctx.get("sms_inbound"))
    marketing = bool(args.get("consent_to_marketing"))  # explicit only; texting us first is not marketing consent

    phone = normalize_phone(phone_raw, settings.default_country_code) or ""
    email_ok = is_email(email)
    if not (email_ok or phone):
        return {"ok": False, "error": "Need a valid phone number or email address. Ask the visitor for one."}
    if ctx.get("dry_run"):
        return {"ok": True, "note": "(dry run) lead would be saved"}

    row = await db.pool().fetchrow(
        """
        INSERT INTO leads (tenant_id, conversation_id, name, email, phone, message, channel,
                           page_url, utm, webhook_status, consent_contact, consent_marketing,
                           consent_marketing_basis, consent_marketing_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12,
                CASE WHEN $12 THEN 'visitor agreed to promotions in ' || $7 || ' conversation' ELSE '' END,
                CASE WHEN $12 THEN now() END)
        RETURNING *
        """,
        tenant["id"],
        ctx.get("conversation_id"),
        name,
        email if email_ok else "",
        phone,
        message,
        ctx.get("channel", "chat"),
        ctx.get("page_url"),
        json.dumps(ctx.get("utm") or {}),
        "pending" if tenant.get("lead_webhook_url") else "none",
        consent,
        marketing,
    )
    await automation.on_lead_created(tenant, dict(row))
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


async def _check_availability(tenant: dict, args: dict, ctx: dict) -> dict:
    return await booking.availability(tenant, str(args.get("date") or ""))


async def _book_appointment(tenant: dict, args: dict, ctx: dict) -> dict:
    return await booking.book(tenant, args, ctx)


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
    "check_availability": _check_availability,
    "book_appointment": _book_appointment,
    "search_knowledge": _search_knowledge,
}


async def run_tool(tenant: dict, name: str, args: dict, ctx: dict) -> dict:
    handler = _HANDLERS.get(name)
    spec = next((s for s in TOOL_SPECS if s["name"] == name), None)
    if handler is None or spec is None or not spec["available"](tenant):
        return {"ok": False, "error": f"Unknown tool: {name}"}
    args = args if isinstance(args, dict) else {}
    try:
        result = await handler(tenant, args, ctx)
    except Exception:  # a tool failure must not break the conversation
        log.exception("tool %s failed", name)
        result = {"ok": False, "error": "Tool failed. Apologise briefly and offer to take contact details."}
    # Trace for evals and for the quote-guard's evidence.
    ctx.setdefault("tool_calls", []).append({"name": name, "args": args, "ok": bool(result.get("ok"))})
    ctx.setdefault("tool_results", []).append(json.dumps(result, default=str))
    return result
