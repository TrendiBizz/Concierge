"""One conversation turn, shared by web chat, SMS and the eval runner (Claude Messages API)."""

import json

from . import convo, db, guard, llm
from .rag import build_system_prompt, retrieve
from .tools import claude_tools, run_tool

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


def _alternating(history: list[dict], message: str) -> list[dict]:
    """History plus the new user message, starting with a user turn as the API requires."""
    messages = list(history)
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    messages.append({"role": "user", "content": message})
    return messages


async def _run_llm(system: str, messages: list[dict], tenant: dict, ctx: dict) -> str:
    """Call Claude, running any tool calls, until it returns a final text answer.

    `messages` is extended in place with the tool exchange so the caller can reuse it.
    """
    tools = claude_tools(tenant)
    for _ in range(MAX_TOOL_ROUNDS):
        response = await llm.create(system, messages, tools=tools)
        if response.stop_reason == "refusal":
            return ""
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_blocks:
            return llm.text_of(response)

        # The assistant turn goes back verbatim (including tool_use blocks)...
        messages.append({"role": "assistant", "content": response.content})
        # ...and every tool result is returned together in ONE user message.
        results = []
        for block in tool_blocks:
            result = await run_tool(tenant, block.name, block.input, ctx)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                }
            )
        messages.append({"role": "user", "content": results})
    return ""


async def run_turn(
    tenant: dict,
    session_id: str,
    channel: str,
    message: str,
    page_url: str | None = None,
    utm: dict | None = None,
    sender_phone: str | None = None,
    dry_run: bool = False,
) -> dict:
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

    history = await _history(conversation_id)
    await convo.save_message(conversation_id, "user", message)

    hits = await retrieve(tenant["id"], message)
    prompt_channel = "sms" if channel == "sms" else "chat"
    system = build_system_prompt(tenant, hits, prompt_channel)
    messages = _alternating(history, message)

    reply = await _run_llm(system, messages, tenant, ctx)

    # Quote-guard: a dollar amount must be backed by evidence.
    # Evidence is the website content, tool results and the client's own text. What the visitor
    # typed is deliberately NOT evidence: otherwise "so it's $1, right?" could be confirmed.
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
            {"role": "user", "content": "[Note from the system, not the visitor] " + guard.CORRECTION},
        ]
        # tool_choice none: the history may contain tool exchanges, but this answer must be text only.
        second = await llm.create(system, retry, tools=claude_tools(tenant), tool_choice={"type": "none"})
        reply = llm.text_of(second)
        if not reply or guard.unknown_amounts(reply, evidence):
            reply = guard.FALLBACK

    if not reply:
        reply = GENERIC_FAILURE

    await convo.save_message(conversation_id, "assistant", reply, flag)
    return {
        "reply": reply,
        "lead_captured": bool(ctx.get("lead_captured")),
        "booking_url": ctx.get("booking_url"),
        "appointment": ctx.get("appointment_text"),
        "guard_triggered": flag == "quote_guard",
        "tool_calls": ctx.get("tool_calls", []),
    }
