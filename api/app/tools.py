"""Tools the AI can call. Shared by text chat / SMS (OpenAI format) and Grok Voice (flat format).

Every tool executes server-side and is scoped to the tenant that owns the public key, so the
browser can never read another client's data. Which tools exist depends on the tenant: native
booking tools only appear when the client has turned native booking on.
"""

import json
import logging

from . import automation, booking, casetimeline, db
from .config import get_settings
from .contact import is_email, normalize_phone
from .rag import retrieve, tag_url

log = logging.getLogger("concierge.tools")

TOOL_SPECS: list[dict] = [
    {
        "name": "request_enquiry_acknowledgement",
        "description": "Ask whether the enquirer wants a separate acknowledgement. If declined use requested=false. Otherwise ask for channel and recipient, call with confirmed=false, read back the result, wait for yes, then call with the same recipient/channel and confirmed=true. This is separate from notifying the business owner. Never claim a queued message was received.",
        "parameters": {"type": "object", "properties": {
            "requested": {"type": "boolean"}, "channel": {"type": "string", "enum": ["email", "sms"]},
            "recipient": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["requested"]},
        "voice": True, "chat": True, "available": lambda t: True,
    },
    {
        "name": "request_conversation_copy",
        "description": "Request a copy after this voice conversation is saved. First capture_lead with the caller's contact and permission. Read back that recipient, whether they want saved text or the recording link, and SMS or email. Call with confirmed=true only after their clear yes. A requested or queued response never means sent.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": ["sms", "email"]},
                "content": {"type": "string", "enum": ["text", "recording"]},
                "confirmed": {"type": "boolean"},
            },
            "required": ["channel", "content", "confirmed"],
        },
        "voice": True,
        "chat": False,
        # Needs a voice session in the tool context to attach the delivery request to.
        # A telephone call serves one too, so this is no longer website-only.
        "requires_session": True,
        "available": lambda t: True,
    },
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
        "name": "search_catalog",
        "description": (
            "Look up products in the business catalogue: sale price, unit and stock. "
            "Cost price is never available. Use for product, price and availability questions. "
            "A quotation built from this is only a draft until the owner reviews and signs it."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Product name, SKU or description words"}},
            "required": ["query"]},
        "voice": True, "chat": True, "available": lambda t: True,
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


def voice_tools(tenant: dict, *, website=False) -> list[dict]:
    return [
        {"type": "function", **{k: s[k] for k in ("name", "description", "parameters")}}
        for s in TOOL_SPECS
        if s["voice"] and s["available"](tenant) and (website or not s.get("requires_session"))
    ]


async def _capture_lead(tenant: dict, args: dict, ctx: dict) -> dict:
    settings = get_settings()
    name = str(args.get("name") or "").strip()[:120]
    email = str(args.get("email") or "").strip()[:200]
    phone_raw = str(args.get("phone") or ctx.get("sender_phone") or "").strip()[:40]
    message = str(args.get("message") or "").strip()[:1000]
    consent = bool(args.get("consent_to_contact")) or bool(ctx.get("sms_inbound"))
    marketing = bool(args.get("consent_to_marketing"))  # explicit only; texting us first is not marketing consent

    phone = normalize_phone(phone_raw, casetimeline.tenant_country_code(tenant)) or ""
    email_ok = is_email(email)
    if not (email_ok or phone):
        return {"ok": False, "error": "Need a valid phone number or email address. Ask the visitor for one."}
    if ctx.get("dry_run"):
        return {"ok": True, "note": "(dry run) lead would be saved"}

    # A visitor who gives an email or a number is a customer, not just a lead row. Reconcile the
    # case BEFORE writing the lead, so their next email or call is recognised as the same person
    # instead of arriving as a stranger with a duplicate history.
    case = await casetimeline.reconcile(
        tenant["id"], phone=phone, email=email if email_ok else "", name=name,
        default_cc=casetimeline.tenant_country_code(tenant), source=ctx.get("channel", "chat"))
    case_id = case["id"] if case else None

    # Enquiries captured at channel ingress already exist before the AI runs.
    # Enrich that record instead of creating a duplicate when the caller gives details.
    if ctx.get("conversation_id"):
        existing = await db.pool().fetchrow(
            "UPDATE leads SET name=CASE WHEN $3<>'' THEN $3 ELSE name END, "
            "email=CASE WHEN $4<>'' THEN $4 ELSE email END, "
            "phone=CASE WHEN $5<>'' THEN $5 ELSE phone END, message=$6, "
            "consent_contact=consent_contact OR $7, consent_marketing=consent_marketing OR $8, "
            "consent_marketing_basis=CASE WHEN $8 THEN 'visitor agreed to promotions in conversation' ELSE consent_marketing_basis END, "
            "consent_marketing_at=CASE WHEN $8 THEN COALESCE(consent_marketing_at,now()) ELSE consent_marketing_at END, updated_at=now() "
            "WHERE id=(SELECT id FROM leads WHERE tenant_id=$1 AND conversation_id=$2 "
            "ORDER BY created_at LIMIT 1) RETURNING *",
            tenant["id"], ctx["conversation_id"], name, email if email_ok else "", phone, message, consent, marketing)
        if existing:
            if case_id:
                await db.pool().execute("UPDATE leads SET case_id=$2 WHERE id=$1",
                                        existing["id"], case_id)
                existing = dict(existing, case_id=case_id)
            await automation.lead_followup(tenant, dict(existing))
            ctx["lead_captured"] = True
            return {"ok": True, "note": "Enquiry updated in the CRM. The team can follow up."}

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
    if case_id and row:
        await db.pool().execute("UPDATE leads SET case_id=$2 WHERE id=$1", row["id"], case_id)
        row = dict(row, case_id=case_id)
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


async def _search_catalog(tenant: dict, args: dict, ctx: dict) -> dict:
    """Catalogue lookup. Sale price and stock only; cost never leaves the DB."""
    query = str(args.get("query") or "").strip()[:120]
    if not query:
        return {"ok": False, "error": "Ask for a product name or SKU first."}
    rows = await db.pool().fetch(
        """SELECT sku,name,description,unit,sale_price_cents,stock_quantity
           FROM products
           WHERE tenant_id=$1 AND active
             AND (name ILIKE $2 OR sku ILIKE $2 OR description ILIKE $2)
           ORDER BY name LIMIT 10""",
        tenant["id"], f"%{query}%")
    products = [{
        "sku": row["sku"],
        "name": row["name"],
        "description": row["description"][:300],
        "unit": row["unit"],
        "sale_price": f"{row['sale_price_cents'] / 100:.2f}",
        "sale_price_cents": row["sale_price_cents"],
        "stock": row["stock_quantity"],
        "in_stock": row["stock_quantity"] > 0,
    } for row in rows]
    return {"ok": True, "found": len(products), "products": products}


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


async def _request_conversation_copy(tenant: dict, args: dict, ctx: dict) -> dict:
    from fastapi import HTTPException
    from . import voice_records
    session = ctx.get("voice_session")
    if not session:
        return {"ok": False, "error": "A verified website voice session is required"}
    try:
        return await voice_records.request_delivery(session, tenant,
            channel=args.get("channel"), content=args.get("content"), confirmed=args.get("confirmed"))
    except HTTPException as exc:
        return {"ok": False, "error": exc.detail}


async def _request_ack(tenant, args, ctx):
    from . import acknowledgements
    return await acknowledgements.request(tenant, args, ctx)


_HANDLERS = {
    "request_enquiry_acknowledgement": _request_ack,
    "request_conversation_copy": _request_conversation_copy,
    "capture_lead": _capture_lead,
    "get_booking_link": _get_booking_link,
    "check_availability": _check_availability,
    "book_appointment": _book_appointment,
    "search_knowledge": _search_knowledge,
    "search_catalog": _search_catalog,
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
