"""Live call supervision — the Switchboard, narrowed to what this stack can actually do.

Competitor-gap item B. Octovox's whole pitch is a console where a human watches calls in progress
and takes over in one click. Two facts shape what is honest to build here:

  * The API is already inside the media path for every Grok SIP call (`phone_sip.serve_call`
    receives every transcript event and writes it with `convo.save_message`), so a live transcript
    costs nothing but a read.
  * The provider's SIP call API exposes call control (accept/hangup), **not** a SIP transfer or
    an audio join. Pretending otherwise would be a lie in the UI.

So the console has two engines, and it says which one a call is on:

  * **Grok SIP calls** (`sip:`) — "take over" stops the AI, alerts the owner with the transcript,
    files a callback task and ends the call. No audio join exists on that path.
  * **Asterisk calls** (`ast:`, the Hero DID) — the PBX owns the media, so call control is real:
    the caller is redirected to the owner through the carrier trunk (take-over), or the owner's
    phone is joined to the live call with `ChanSpy` (listen-in, whisper, join). See
    ``call_control``.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from . import asterisk_ami, call_control, casetimeline, db, owner_notifications
from . import supervision as supervision_audit
from .config import get_settings

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


def engine(call: dict) -> str:
    call_sid = call.get("call_sid") or ""
    if call_sid.startswith("ast:"):
        return "asterisk"
    if call_sid.startswith("sip:"):
        return "sip"
    return "unknown"


def summarise(call: dict, turns: list[dict], now: datetime | None = None,
              media_control: bool = False, supervision: list[dict] | None = None) -> dict:
    """One call as the console shows it. Pure, so the list and the drill-down cannot disagree."""
    tail = transcript_tail(turns)
    asterisk = engine(call) == "asterisk"
    return {
        "call_sid": call.get("call_sid"),
        "caller": caller_label(call),
        "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
        "seconds": seconds_in_call(call, now),
        "turns": len(turns),
        "caller_has_spoken": any(turn.get("role") == "user" for turn in turns),
        "transcript": tail,
        "ring_back_available": (call.get("call_sid") or "").startswith("sip:"),
        "engine": engine(call),
        # What the console may honestly offer for this call, on this engine, right now.
        "media_control": {
            "transfer": asterisk and media_control,
            "listen": asterisk and media_control,
            "whisper": asterisk and media_control,
            "join": asterisk and media_control,
            "ring_back": True,
        },
        # Who is listening right now — the console shows it and the audit trail owns it.
        "supervision": [supervision_audit.summarise(row, now)
                        for row in (supervision or [])],
    }


async def active(tenant_id, now: datetime | None = None, limit: int = 20) -> list[dict]:
    await supervision_audit.close_ended_calls(tenant_id)
    rows = await db.pool().fetch(
        """SELECT * FROM phone_calls
           WHERE tenant_id = $1 AND status = 'in_progress'
             AND (started_at IS NULL OR started_at > now() - interval '4 hours')
           ORDER BY started_at DESC LIMIT $2""",
        tenant_id, max(1, min(limit, 50)),
    )
    legs = await supervision_audit.active_by_call(tenant_id)
    calls = []
    for row in rows:
        call = dict(row)
        if not is_live(call, now):
            continue
        calls.append(summarise(call, await _turns(tenant_id, call.get("session_id")), now,
                               media_control=call_control.enabled(),
                               supervision=legs.get(str(call.get("call_sid")), [])))
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
    await supervision_audit.close_ended_calls(tenant_id)
    call = dict(row)
    data = summarise(call, await _turns(tenant_id, call.get("session_id")),
                     media_control=call_control.enabled(),
                     supervision=await supervision_audit.open_for_call(tenant_id, call_sid))
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
        default_cc=casetimeline.tenant_country_code(tenant), source="voice",
    )
    paused = False
    if case:
        paused = await casetimeline.set_takeover(
            tenant["id"], case_key=case["case_key"], paused=True,
            by=f"{by}: live call takeover",
        )
    turns = await _turns(tenant["id"], call.get("session_id"))
    tail = "\n".join(f"{t['who']}: {t['text']}" for t in transcript_tail(turns, limit=6))
    text_only = text_only_owner(tenant)
    follow_up = "Reply to them by text or email now." if text_only else "Ring them back now."
    await owner_notifications.queue(
        tenant,
        f"Take over now: {caller}",
        f"You asked to take over a live call from {caller}.\n"
        f"We have stopped Concierge on this call. {follow_up}\n\n{tail}\n",
        f"takeover:{call.get('call_sid')}",
    )
    await _callback_task(tenant["id"], case, caller, tail, call, text_only=text_only)
    transferred = False
    if engine(call) == "asterisk":
        try:
            number = await owner_voice_number(tenant)
            if not number:
                raise call_control.CallControlUnavailable(
                    "No owner phone number is set for transfers")
            await call_control.transfer_call(call["call_sid"], tenant["slug"], number)
            transferred, ended, note = True, False, ""
        except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
            # The alert and callback task are already filed; say plainly why the audio
            # hand-over did not happen instead of pretending the caller was transferred.
            ended, note = False, f"The call could not be transferred: {error}. {follow_up}"
            log.warning("asterisk take-over failed for %s: %s", caller, error)
    else:
        ended, note = await _hang_up(call)
    log.info("live takeover by %s for %s (paused=%s, transferred=%s, ended=%s)",
             by, caller, paused, transferred, ended)
    return {"caller": caller, "paused": paused, "ended": ended, "transferred": transferred,
            "note": note, "engine": engine(call),
            "case_key": case["case_key"] if case else None}


def text_only_owner(tenant: dict) -> bool:
    """The owner works in writing only: every hand-off message must say "reply", never "ring"."""
    return bool(tenant.get("owner_text_only"))


async def owner_voice_number(tenant: dict) -> str:
    """The number a human can be rung on for this business.

    Managed setup first, then the dedicated call number (`owner_call_phone`), and only then the
    alert number: alerts and transfers used to share `notify_phone`, which a text-first owner
    cannot separate.
    """
    row = await db.pool().fetchrow(
        "SELECT owner_number FROM managed_phone_setups WHERE tenant_id = $1", tenant["id"])
    number = ((row["owner_number"] if row else "") or tenant.get("owner_call_phone")
              or tenant.get("notify_phone") or "").strip()
    return number if re.fullmatch(r"\+?[0-9]{3,20}", number) else ""


async def supervise(tenant: dict, call: dict, mode: str, *, supervisor: str = "owner") -> dict:
    """Join the owner's phone to a live Asterisk call: listen, whisper, or join.

    The audit row is opened *before* the phone is dialled, so an attempted listen that never
    connected is still on the record (with a zero duration and the reason). If the ring fails the
    row is closed immediately and the error propagates — the console must not show a listener who
    is not there.
    """
    if engine(call) != "asterisk":
        raise call_control.CallControlUnavailable(
            "Listen-in needs the Asterisk line; this call is on the SIP provider")
    options = call_control.spy_options(mode)
    number = await owner_voice_number(tenant)
    if not number:
        raise call_control.CallControlUnavailable("No owner phone number is set for supervision")
    mode = str(mode).strip().lower()
    marker = secrets.token_hex(8)
    record = await supervision_audit.start(
        tenant["id"], call["call_sid"], mode,
        supervisor=supervisor, number=number, marker=marker)
    try:
        channel = await call_control.attach_supervisor(
            call["call_sid"], number, mode, channel_dial=get_settings().asterisk_channel_dial,
            spy_marker=marker)
    except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
        await supervision_audit.stop(tenant["id"], record["id"],
                                     f"{supervision_audit.RING_FAILED}: {error}")
        raise
    await supervision_audit.attach_channel(record["id"], channel)
    log.info("supervisor %s on %s (%s, id=%s)", number, channel, mode, record["id"])
    return {"mode": mode, "channel": channel, "number": number, "options": options,
            "engine": "asterisk", "supervision_id": record["id"],
            "supervision": {"id": record["id"], "mode": mode,
                            "supervisor": supervisor, "open": True}}


async def stop_supervision(tenant: dict, call_sid: str, *, by: str = "owner") -> dict:
    """End every supervision leg on this call and close its audit rows."""
    legs = await supervision_audit.open_for_call(tenant["id"], call_sid)
    if not legs:
        return {"stopped": 0, "note": "Nobody is listening to this call."}
    live = None
    stopped = 0
    for row in legs:
        marker = (row.get("marker") or "").strip()
        channels = []
        if marker:
            # The marker is the leg's identity: the PBX can be asked which channel carries it.
            # This is preferred over the stored name because the originate can return before the
            # leg is listed, and a Local leg is a pair of channels.
            try:
                live = live if live is not None else await call_control.spy_legs()
            except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
                log.warning("could not ask the PBX for supervision legs: %s", error)
                live = {}
            channels = [name for name, value in live.items() if value == marker]
        if not channels:
            channel = (row.get("spy_channel") or "").strip()
            if channel:
                channels = [channel]
        for channel in channels:
            try:
                await call_control.hangup_leg(channel)
            except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
                # The row still closes: the console stops claiming a listener either way, and
                # the reconcile pass will notice if the leg outlives it.
                log.warning("could not hang up supervision leg %s: %s", channel, error)
        if await supervision_audit.stop(tenant["id"], row["id"],
                                        f"{supervision_audit.STOPPED} ({by})"):
            stopped += 1
    log.info("supervision stopped by %s on %s (%s leg(s))", by, call_sid, stopped)
    return {"stopped": stopped, "note": ""}


async def reconcile_supervision(tenant_id) -> int:
    """Close legs whose call ended, and legs the PBX no longer carries (the phone hung up)."""
    closed = await supervision_audit.close_ended_calls(tenant_id)
    open_legs = await supervision_audit.active_by_call(tenant_id)
    if not open_legs or not call_control.enabled():
        return closed
    try:
        live = await call_control.spy_legs()
    except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
        # The audit trail must never fail a page load because the PBX is briefly unavailable;
        # the legs stay open and the next read tries again.
        log.warning("supervision reconcile skipped: %s", error)
        return closed
    return closed + await supervision_audit.close_missing_legs(tenant_id, live)


async def _callback_task(tenant_id, case, caller: str, tail: str, call: dict,
                         text_only: bool = False) -> None:
    lead_id = None
    if case:
        lead_id = await db.pool().fetchval(
            "SELECT id FROM leads WHERE tenant_id = $1 AND case_id = $2 "
            "ORDER BY created_at DESC LIMIT 1", tenant_id, case["id"])
    title = f"Reply to: {caller}" if text_only else f"Ring back: {caller}"
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
