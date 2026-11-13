"""One conversation turn, shared by web chat, SMS and the eval runner."""

import asyncio
import json
import logging
from types import SimpleNamespace

from . import casetimeline, convo, db, guard, llm, enquiries, owner_notifications, tenant_pause
import hashlib
from .rag import build_system_prompt, retrieve
from .tools import chat_tools, run_tool

log = logging.getLogger("concierge.chat")

MAX_TOOL_ROUNDS = 4
# Independent lookups can run concurrently; anything that mutates stays ordered.
READ_ONLY_TOOLS = {"search_knowledge", "check_availability", "get_booking_link"}
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


def _parse_args(tc) -> dict:
    try:
        parsed = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _execute_tools(tool_calls, tenant: dict, ctx: dict) -> list:
    """Run one assistant turn's tool calls. Read-only lookups run concurrently."""
    results: list = [None] * len(tool_calls)
    parallel = [i for i, tc in enumerate(tool_calls) if tc.function.name in READ_ONLY_TOOLS]
    sequential = [i for i, tc in enumerate(tool_calls) if tc.function.name not in READ_ONLY_TOOLS]
    if parallel:
        gathered = await asyncio.gather(*[
            run_tool(tenant, tool_calls[i].function.name, _parse_args(tool_calls[i]), ctx)
            for i in parallel
        ])
        for index, result in zip(parallel, gathered):
            results[index] = result
    for index in sequential:
        results[index] = await run_tool(
            tenant, tool_calls[index].function.name, _parse_args(tool_calls[index]), ctx)
    return results


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
        results = await _execute_tools(msg.tool_calls, tenant, ctx)
        for tc, result in zip(msg.tool_calls, results):
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
    return ""


def suppressed(reason: str, conversation_id=None, reply: str = "") -> dict:
    """The one shape for "we produce no answer".

    Every caller reads `reply`, `lead_captured`, `booking_url` and `appointment` off the result,
    so a suppression that returned only some of them made the chat endpoint raise a KeyError and
    answer the visitor with a 502 -- a human takeover looked like a broken website. One shape,
    one place.
    """
    return {
        "reply": reply,
        "suppressed": True,
        "reason": reason,
        "conversation_id": conversation_id,
        "lead_captured": False,
        "booking_url": None,
        "appointment": None,
        "guard_triggered": False,
        "tool_calls": [],
    }


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
            return suppressed("human_takeover")

    # The business owner may have switched Concierge off entirely. Take the message, answer
    # nothing, and never reach the model: a pause that still costs a model call is not a pause.
    if not dry_run:
        try:
            tenant_off = await tenant_pause.is_paused(tenant)
        except Exception:  # noqa: BLE001 - is_paused already fails open; belt and braces
            log.exception("pause lookup failed for tenant %s", tenant.get("slug"))
            tenant_off = False
        if tenant_off:
            conversation_id = await convo.get_or_create(tenant, session_id, channel, page_url, utm)
            if channel == "chat":
                await enquiries.capture(tenant, "chat", str(conversation_id), message,
                                        conversation_id=conversation_id)
            await convo.save_message(conversation_id, "user", message)
            return suppressed("tenant_paused", conversation_id,
                              tenant_pause.HOLDING_REPLY if channel == "chat" else "")

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
    # Email is only a generated draft here; outbox marks it answered after a successful send.
    # Direct chat/SMS responses are returned to their channel caller in this turn.
    if not dry_run and channel != "email":
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


async def run_turn_stream(
    tenant: dict,
    session_id: str,
    channel: str,
    message: str,
    page_url: str | None = None,
    utm: dict | None = None,
):
    """Same turn as run_turn, but yields token events while the final answer streams.

    Events: {"type":"token","text":...}, {"type":"replace","text":...},
    {"type":"done", ...}. The reply is saved once, after the guard, so the
    stored message always matches what the visitor ends up seeing.
    """
    try:
        paused = await casetimeline.is_paused_for(
            tenant["id"], phone="", email="",
            default_cc=casetimeline.tenant_country_code(tenant),
        )
    except Exception:  # noqa: BLE001 - a lookup failure must not silence the assistant
        log.exception("takeover lookup failed for tenant %s", tenant.get("slug"))
        paused = False
    if paused:
        yield {"type": "done", "reply": "", "suppressed": True, "reason": "human_takeover"}
        return

    # The streaming path is a separate implementation, so the owner's pause has to be honoured
    # here too -- otherwise a business that switched Concierge off keeps answering on the widget.
    try:
        tenant_off = await tenant_pause.is_paused(tenant)
    except Exception:  # noqa: BLE001
        log.exception("pause lookup failed for tenant %s", tenant.get("slug"))
        tenant_off = False
    if tenant_off:
        conversation_id = await convo.get_or_create(tenant, session_id, channel, page_url, utm)
        if channel == "chat":
            await enquiries.capture(tenant, "chat", str(conversation_id), message,
                                    conversation_id=conversation_id)
        await convo.save_message(conversation_id, "user", message)
        yield {"type": "done", "reply": tenant_pause.HOLDING_REPLY, "suppressed": True,
               "reason": "tenant_paused", "conversation_id": conversation_id}
        return

    conversation_id = await convo.get_or_create(tenant, session_id, channel, page_url, utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": channel,
        "page_url": page_url,
        "utm": convo.clean_utm(utm),
        "sender_phone": None,
        "sms_inbound": False,
        "dry_run": False,
    }
    if channel == "chat":
        await enquiries.capture(tenant, "chat", str(conversation_id), message, conversation_id=conversation_id)
    history = await _history(conversation_id)
    await convo.save_message(conversation_id, "user", message)

    hits = await retrieve(tenant["id"], message)
    prompt_channel = "sms" if channel == "sms" else ("email" if channel == "email" else "chat")
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(tenant, hits, prompt_channel)}]
    messages += history
    messages.append({"role": "user", "content": message})

    reply = ""
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        content = ""
        slots: dict[int, dict] = {}
        tools = chat_tools(tenant) if round_no < MAX_TOOL_ROUNDS else None
        async for delta in llm.stream_complete(messages, tools=tools):
            if delta.content:
                content += delta.content
                yield {"type": "token", "text": delta.content}
            for tc in (delta.tool_calls or []):
                slot = slots.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
        if slots and round_no < MAX_TOOL_ROUNDS:
            calls = [
                SimpleNamespace(
                    id=slot["id"] or f"call_{index}",
                    function=SimpleNamespace(name=slot["name"], arguments=slot["arguments"]),
                )
                for index, slot in sorted(slots.items())
            ]
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {"id": call.id, "type": "function",
                     "function": {"name": call.function.name, "arguments": call.function.arguments}}
                    for call in calls
                ],
            })
            results = await _execute_tools(calls, tenant, ctx)
            for call, result in zip(calls, results):
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, default=str)})
            continue
        reply = content.strip()
        break

    flag = None
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
        corrected = (second.content or "").strip()
        if not corrected or guard.unknown_amounts(corrected, evidence):
            corrected = guard.FALLBACK
        reply = corrected
        yield {"type": "replace", "text": reply}
    if not reply:
        reply = GENERIC_FAILURE
        yield {"type": "replace", "text": reply}

    await convo.save_message(conversation_id, "assistant", reply, flag)
    if channel != "email":
        await casetimeline.mark_replied(
            tenant["id"], phone="", email="", channel=channel,
            default_cc=casetimeline.tenant_country_code(tenant),
        )
    rows = await db.pool().fetch(
        "SELECT role,content FROM messages WHERE conversation_id=$1 ORDER BY id", conversation_id)
    dialogue = "\n\n".join(
        ("Enquirer" if row["role"] == "user" else "Concierge") + ": " + row["content"] for row in rows)
    lead = await db.pool().fetchval(
        "SELECT id FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1",
        tenant["id"], conversation_id)
    key = hashlib.sha256((str(conversation_id) + message + reply).encode()).hexdigest()
    await owner_notifications.queue(
        tenant, channel.title() + " conversation for " + tenant["name"], dialogue,
        f"dialogue:{tenant['id']}:{key}", lead_id=lead)
    yield {
        "type": "done",
        "conversation_id": conversation_id,
        "lead_captured": bool(ctx.get("lead_captured")),
        "booking_url": ctx.get("booking_url"),
        "appointment": ctx.get("appointment_text"),
        "guard_triggered": flag == "quote_guard",
        "reply": reply,
    }
