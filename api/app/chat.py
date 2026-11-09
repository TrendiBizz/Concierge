"""One conversation turn, shared by web chat, SMS and the eval runner."""

import json
import logging

from . import casetimeline, convo, db, guard, llm, enquiries, owner_notifications
import hashlib
from .rag import build_system_prompt, retrieve
from .tools import chat_tools, run_tool

log = logging.getLogger("concierge.chat")

MAX_TOOL_ROUNDS = 4
GENERIC_FAILURE = (
    "Sorry, I had trouble with that. Could you rephrase, or leave your phone number or email so "
    "the team can follow up?"
)


async def _history(conversation_id) -> list[dict]:
    rows = await db.pool().fetch(
        """
        SELECT role, content FROM (
            SELECT id, role, content FROM messages WHERE conversation_id = $1 ORDER BY id DESC LIMIT 10
        ) recent ORDER BY id
        """,
        conversation_id,
    )
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _run_llm(messages: list[dict], tenant: dict, ctx: dict) -> str:
    """Call the model, executing tool calls, until it produces a final text answer."""
    for _ in range(MAX_TOOL_ROUNDS):
        msg = await llm.complete(messages, tools=chat_tools(tenant))
        if not msg.tool_calls:
            return (msg.content or "").strip()
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await run_tool(tenant, tc.function.name, args, ctx)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
    return ""


async def run_turn(
    tenant: dict,
    session_id: str,
    channel: str,
    message: str,
    page_url: str | None = None,
    utm: dict | None = None,
    sender_phone: str | None = None,
    sender_email: str | None = None,
    dry_run: bool = False,
) -> dict:
    # Human takeover: if the owner has personally taken over this customer, produce no AI reply.
    # This runs BEFORE any model call, so a takeover costs nothing and cannot be raced.
    # dry_run is exempt: eval scenarios must still exercise the model, and a dry run sends nothing.
    if not dry_run:
        try:
            paused = await casetimeline.is_paused_for(
                tenant["id"], phone=sender_phone or "", email=sender_email or "",
                default_cc=casetimeline.tenant_country_code(tenant),
            )
        except Exception:  # noqa: BLE001 - a lookup failure must not silence the assistant
            log.exception("takeover lookup failed for tenant %s", tenant.get("slug"))
            paused = False
        if paused:
            return {"reply": "", "suppressed": True, "reason": "human_takeover", "conversation_id": None}

    conversation_id = await convo.get_or_create(tenant, session_id, channel, page_url, utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": channel,
        "page_url": page_url,
        "utm": convo.clean_utm(utm),
        "sender_phone": sender_phone,
        "sms_inbound": channel == "sms",
        "dry_run": dry_run,
    }

    if channel == 'chat' and not dry_run:
        await enquiries.capture(tenant, 'chat', str(conversation_id), message, conversation_id=conversation_id)
    history = await _history(conversation_id)
    await convo.save_message(conversation_id, "user", message)

    hits = await retrieve(tenant["id"], message)
    prompt_channel = "voice" if channel in ("voice", "phone") else ("sms" if channel == "sms" else ("email" if channel == "email" else "chat"))
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(tenant, hits, prompt_channel)}]
    if sender_email:
        messages.append({"role": "system", "content": "Reply address supplied by authenticated email ingress: " + sender_email})
    messages += history
    messages.append({"role": "user", "content": message})

    reply = await _run_llm(messages, tenant, ctx)

    # Quote-guard: a dollar amount must be backed by evidence.
    flag = None
    # Evidence is the website content, tool results and the client's own text. What the visitor
    # typed is deliberately NOT evidence: otherwise "so it's $1, right?" could be confirmed.
    evidence = "\n".join(
        [h["content"] for h in hits]
        + ctx.get("tool_results", [])
        + [tenant.get("persona") or "", tenant.get("incentive") or ""]
    )
    if reply and guard.unknown_amounts(reply, evidence):
        flag = "quote_guard"
        retry = list(messages) + [
            {"role": "assistant", "content": reply},
            {"role": "system", "content": guard.CORRECTION},
        ]
        second = await llm.complete(retry, tools=None)
        reply = (second.content or "").strip()
        if not reply or guard.unknown_amounts(reply, evidence):
            reply = guard.FALLBACK

    if not reply:
        reply = GENERIC_FAILURE

    await convo.save_message(conversation_id, "assistant", reply, flag)
    # The reply answers the customer, so the unified timeline must stop counting the message as
    # unanswered. Best effort: bookkeeping must never break a delivery that already succeeded.
    if not dry_run:
        await casetimeline.mark_replied(
            tenant["id"], phone=sender_phone or "", email=sender_email or "", channel=channel,
            default_cc=casetimeline.tenant_country_code(tenant),
        )
    if channel in ('chat', 'sms', 'email') and not dry_run:
        rows = await db.pool().fetch('SELECT role,content FROM messages WHERE conversation_id=$1 ORDER BY id', conversation_id)
        dialogue = '\n\n'.join(('Enquirer' if row['role']=='user' else 'Concierge') + ': ' + row['content'] for row in rows)
        lead = await db.pool().fetchval('SELECT id FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], conversation_id)
        key = hashlib.sha256((str(conversation_id) + message + reply).encode()).hexdigest()
        await owner_notifications.queue(tenant, channel.title() + ' conversation for ' + tenant['name'], dialogue,
                                        f"dialogue:{tenant['id']}:{key}", lead_id=lead)
    return {
        "reply": reply,
        "lead_captured": bool(ctx.get("lead_captured")),
        "booking_url": ctx.get("booking_url"),
        "appointment": ctx.get("appointment_text"),
        "guard_triggered": flag == "quote_guard",
        "tool_calls": ctx.get("tool_calls", []),
    }
