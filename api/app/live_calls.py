"""Live call supervision — the Switchboard, narrowed to what this stack can actually do.

Competitor-gap item B. Octovox's whole pitch is a console where a human watches calls in progress
and takes over in one click. Two facts shape what is honest to build here:

  * The API is already inside the media path for every Grok SIP call (`phone_sip.serve_call`
    receives every transcript event and writes it with `convo.save_message`), so a live transcript
    costs nothing but a read.
  * The provider's call API exposes call control (accept/hangup), **not** a SIP transfer or audio
    join. Pretending otherwise would be a lie in the UI.

So "take over" means, honestly: stop the AI on this call, ring the owner now with the caller's
number and the conversation so far, give them a callback task, and let them dial the caller back.
That is what a small business actually does, and it needs no new provider capability.

No media server, no audio listen-in. That is deliberate: it is the difference between a feature and
an infrastructure project.
"""

import logging
from datetime import datetime, timedelta, timezone

from . import casetimeline, db, owner_notifications

log = logging.getLogger("concierge.live_calls")

LIVE_WINDOW = timedelta(hours=4)
TAIL = 12


def is_live(call: dict, now: datetime | None = None) -> bool:
    """A call the owner may act on: in progress, and started recently enough to be real."""
    now = now or datetime.now(timezone.utc)
    if (call.get("status") or "") != "in_progress":
        return False
    started = call.get("started_at")
    if not started:
        return True
    return now - started <= LIVE_WINDOW


def caller_label(call: dict) -> str:
    return (call.get("from_number") or "").strip() or "Unknown caller"


def seconds_in_call(call: dict, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    started = call.get("started_at")
    if not started:
        return 0
    return max(0, int((now - started).total_seconds()))


def transcript_tail(turns: list[dict], limit: int = TAIL) -> list[dict]:
    """The last few turns, labelled for a human reading them under pressure."""
    rows = []
    for turn in turns[-limit:]:
        role = turn.get("role") or ""
        rows.append({
            "who": "Caller" if role == "user" else "Concierge",
            "role": role,
            "text": (turn.get("content") or "")[:2000],
        })
    return rows


def summarise(call: dict, turns: list[dict], now: datetime | None = None) -> dict:
    """One call as the console shows it. Pure, so the list and the drill-down cannot disagree."""
    tail = transcript_tail(turns)
    return {
        "call_sid": call.get("call_sid"),
        "caller": caller_label(call),
        "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
        "seconds": seconds_in_call(call, now),
        "turns": len(turns),
        "caller_has_spoken": any(turn.get("role") == "user" for turn in turns),
        "transcript": tail,
        "ring_back_available": (call.get("call_sid") or "").startswith("sip:"),
    }


async def active(tenant_id, now: datetime | None = None, limit: int = 20) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT * FROM phone_calls
           WHERE tenant_id = $1 AND status = 'in_progress'
             AND (started_at IS NULL OR started_at > now() - interval '4 hours')
           ORDER BY started_at DESC LIMIT $2""",
        tenant_id, max(1, min(limit, 50)),
    )
    calls = []
    for row in rows:
        call = dict(row)
        if not is_live(call, now):
            continue
        calls.append(summarise(call, await _turns(tenant_id, call.get("session_id")), now))
    return calls


async def _turns(tenant_id, session_id: str | None) -> list[dict]:
    if not session_id:
        return []
    rows = await db.pool().fetch(
        """SELECT m.role, m.content FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.tenant_id = $1 AND c.session_id = $2
           ORDER BY m.id DESC LIMIT 60""",
        tenant_id, session_id,
    )
    return [dict(row) for row in reversed(rows)]


async def one(tenant_id, call_sid: str) -> dict | None:
    row = await db.pool().fetchrow(
        "SELECT * FROM phone_calls WHERE tenant_id = $1 AND call_sid = $2", tenant_id, call_sid)
    if not row:
        return None
    call = dict(row)
    data = summarise(call, await _turns(tenant_id, call.get("session_id")))
    data["live"] = is_live(call)
    return data


async def take_over(tenant: dict, call: dict, *, by: str = "owner") -> dict:
    """Stop the AI on this call and put the human in charge of the customer.

    Ordering matters: the case is paused first (so nothing the assistant does afterwards can
    contradict the owner), then the owner is alerted, then the call is ended. The provider hangup
    is best-effort — if it fails the call is still marked for the owner, and the after-call
    analysis records what happened.
    """
    caller = caller_label(call)
    case = await casetimeline.reconcile(
        tenant["id"], phone=call.get("from_number") or "",
        default_cc=casetimeline.tenant_country_code(tenant),
    )
    paused = False
    if case:
        paused = await casetimeline.set_takeover(
            tenant["id"], case_key=case["case_key"], paused=True,
            by=f"{by}: live call takeover",
        )
    turns = await _turns(tenant["id"], call.get("session_id"))
    tail = "\n".join(f"{t['who']}: {t['text']}" for t in transcript_tail(turns, limit=6))
    await owner_notifications.queue(
        tenant,
        f"Take over now: {caller}",
        f"You asked to take over a live call from {caller}.\n"
        f"We have stopped Concierge on this call. Ring them back now.\n\n{tail}\n",
        f"takeover:{call.get('call_sid')}",
    )
    await _callback_task(tenant["id"], case, caller, tail, call)
    ended, note = await _hang_up(call)
    log.info("live takeover by %s for %s (paused=%s, ended=%s)", by, caller, paused, ended)
    return {"caller": caller, "paused": paused, "ended": ended, "note": note,
            "case_key": case["case_key"] if case else None}


async def _callback_task(tenant_id, case, caller: str, tail: str, call: dict) -> None:
    lead_id = None
    if case:
        lead_id = await db.pool().fetchval(
            "SELECT id FROM leads WHERE tenant_id = $1 AND case_id = $2 "
            "ORDER BY created_at DESC LIMIT 1", tenant_id, case["id"])
    title = f"Ring back: {caller}"
    existing = None
    if lead_id:
        existing = await db.pool().fetchval(
            "SELECT 1 FROM tasks WHERE tenant_id = $1 AND lead_id = $2 AND status = 'open' "
            "AND title = $3 LIMIT 1", tenant_id, lead_id, title)
    if existing:
        return
    await db.pool().execute(
        """INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, case_id)
           VALUES ($1, $2, $3, $4, now(), 'call_back', 'system', $5)""",
        tenant_id, lead_id, title[:200],
        ("You took over a live call.\n\n" + tail)[:1000],
        case["id"] if case else None,
    )


async def _hang_up(call: dict) -> tuple[bool, str]:
    """End the AI call, if we can. Never raises: the alert already went out."""
    call_sid = call.get("call_sid") or ""
    if not call_sid.startswith("sip:"):
        return False, "This call is not on the Grok SIP path; end it from the phone system."
    try:
        from . import phone_sip

        ok = await phone_sip.call_control(call_sid[4:], "hangup")
        return bool(ok), "" if ok else "The provider did not confirm the hangup."
    except Exception:
        log.exception("live takeover hangup failed for %s", call_sid)
        return False, "The provider did not confirm the hangup."
