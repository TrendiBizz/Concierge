"""Native appointment booking: business hours, availability, and confirmed, race-safe booking.

The assistant never invents times. It calls check_availability, offers what the server says is
free, and book_appointment enforces a read-back: the first call only returns a sentence to read
to the visitor; the booking is created only when a second call with confirmed=true arrives for
the same time and name in the same conversation.
"""

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import automation, casetimeline, convo, db, calendar_connection
from .config import get_settings
from .contact import is_email, normalize_phone

log = logging.getLogger(__name__)

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _hm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def day_slots(tenant: dict, day: date, now_utc: datetime, booked: list[tuple[datetime, datetime]]) -> list[datetime]:
    """Free slot start times (UTC) for one local calendar day."""
    tz = ZoneInfo(tenant["timezone"])
    step = timedelta(minutes=tenant["slot_minutes"])
    earliest = now_utc + timedelta(hours=tenant["min_notice_hours"])
    slots: list[datetime] = []
    for opens, closes in tenant["business_hours"].get(DAYS[day.weekday()], []):
        cursor = datetime.combine(day, _hm(opens))
        end = datetime.combine(day, _hm(closes))
        while cursor + step <= end:
            start_utc = cursor.replace(tzinfo=tz).astimezone(timezone.utc)
            end_utc = start_utc + step
            clash = any(b_start < end_utc and b_end > start_utc for b_start, b_end in booked)
            if start_utc.astimezone(tz).replace(tzinfo=None) == cursor and start_utc >= earliest and not clash:
                slots.append(start_utc)
            cursor += step
    return slots


async def _booked(tenant_id, day: date, tz: ZoneInfo, conn=None) -> list[tuple[datetime, datetime]]:
    start = datetime.combine(day, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    runner = conn or db.pool()
    rows = await runner.fetch(
        "SELECT starts_at, ends_at FROM appointments WHERE tenant_id = $1 AND status = 'booked' "
        "AND starts_at < $3 AND ends_at > $2",
        tenant_id, start, end,
    )
    return [(r["starts_at"], r["ends_at"]) for r in rows]


async def _slots_on(tenant: dict, day: date, conn=None) -> list[datetime]:
    tz = ZoneInfo(tenant["timezone"])
    booked = await _booked(tenant["id"], day, tz, conn)
    start = datetime.combine(day, time(0), tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz).astimezone(timezone.utc)
    booked += await calendar_connection.busy(tenant['id'], start, end)
    return day_slots(tenant, day, datetime.now(timezone.utc), booked)


def _parse_local(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace(" ", "T"))


async def availability(tenant: dict, date_str: str) -> dict:
    tz = ZoneInfo(tenant["timezone"])
    try:
        day = date.fromisoformat((date_str or "").strip())
    except ValueError:
        return {"ok": False, "error": "date must be YYYY-MM-DD"}
    today = datetime.now(tz).date()
    last = today + timedelta(days=tenant["max_days_ahead"])
    if day < today or day > last:
        return {"ok": False, "error": f"Bookings are open from {today} to {last}."}

    slots = await _slots_on(tenant, day)
    if slots:
        return {
            "ok": True,
            "date": day.isoformat(),
            "weekday": day.strftime("%A"),
            "timezone": tenant["timezone"],
            "slots": [s.astimezone(tz).strftime("%H:%M") for s in slots][:12],
            "slot_minutes": tenant["slot_minutes"],
        }

    upcoming = []
    probe = day + timedelta(days=1)
    while probe <= last and len(upcoming) < 3 and (probe - day).days <= 14:
        found = await _slots_on(tenant, probe)
        if found:
            upcoming.append({"date": probe.isoformat(), "weekday": probe.strftime("%A"),
                             "first_slot": found[0].astimezone(tz).strftime("%H:%M")})
        probe += timedelta(days=1)
    return {"ok": True, "date": day.isoformat(), "weekday": day.strftime("%A"), "slots": [],
            "message": "No free times that day.", "next_available_dates": upcoming}


async def book(tenant: dict, args: dict, ctx: dict) -> dict:
    tz = ZoneInfo(tenant["timezone"])
    settings = get_settings()

    try:
        start_local = _parse_local(str(args.get("start") or ""))
    except ValueError:
        return {"ok": False, "error": "start must look like 2026-11-05 14:30 (business local time)"}
    name = str(args.get("name") or "").strip()[:120]
    phone_raw = str(args.get("phone") or ctx.get("sender_phone") or "").strip()[:40]
    email = str(args.get("email") or "").strip()[:200]
    notes = str(args.get("notes") or "").strip()[:500]
    consent = bool(args.get("consent_to_contact")) or bool(ctx.get("sms_inbound"))

    phone = normalize_phone(phone_raw, casetimeline.tenant_country_code(tenant)) or ""
    if not name:
        return {"ok": False, "error": "Need the visitor's name."}
    if not (phone or is_email(email)):
        return {"ok": False, "error": "Need a valid phone number or email so we can confirm."}

    if start_local.tzinfo is not None:
        return {"ok": False, "error": "Use business local time without a UTC offset"}
    start_utc = start_local.replace(tzinfo=tz).astimezone(timezone.utc)
    if start_utc.astimezone(tz).replace(tzinfo=None) != start_local:
        return {"ok": False, "error": "That local time does not exist because of daylight saving"}
    conversation_id = ctx.get('conversation_id')
    if conversation_id and args.get('confirmed') is True:
        previous = await db.pool().fetchrow(
            'SELECT * FROM appointments WHERE tenant_id=$1 AND conversation_id=$2 AND starts_at=$3',
            tenant['id'], conversation_id, start_utc)
        if previous:
            if previous['status'] != 'booked':
                return {'ok': False, 'error': 'That earlier booking is no longer active. Ask the team to reschedule or choose a new time.'}
            if previous['name'] != name or previous['email'] != (email if is_email(email) else '') or previous['phone'] != phone:
                return {"ok": False, "error": "A different booking already exists for this conversation and time"}
            return booking_result(tenant, previous, duplicate=True)
    free = await _slots_on(tenant, start_local.date())
    if start_utc not in free:
        return {"ok": False, "error": "That time is not available. Call check_availability and offer a listed slot."}

    # --- Enforced read-back -------------------------------------------------
    conversation_id = ctx.get("conversation_id")
    key = {"start": start_utc.isoformat(), "name": name.lower(), "email": email.lower(), "phone": phone, "consent": consent}
    pending = await convo.get_pending_booking(conversation_id) if conversation_id else None
    if not (args.get("confirmed") is True and pending == key):
        if conversation_id:
            await convo.set_pending_booking(conversation_id, key)
        where = phone or email
        return {
            "ok": False,
            "needs_confirmation": True,
            "read_back": f"{name}, {automation.fmt_local(tenant, start_utc)}. We'll confirm with you at {where}.",
            "instruction": (
                "Read this back to the visitor and ask them to confirm. Only after they clearly say "
                "yes, call book_appointment again with exactly the same start and name and confirmed=true."
            ),
        }

    if ctx.get("dry_run"):
        return {"ok": True, "confirmation": "(dry run) booking would be created"}

    end_utc = start_utc + timedelta(minutes=tenant["slot_minutes"])

    # A booking is a customer, not just a lead row. This path used to write a lead with a name,
    # email and phone and never create a customer record, so somebody who booked an appointment
    # was missing from Contacts entirely. Reconcile first, outside the booking transaction.
    case = await casetimeline.reconcile(
        tenant["id"], phone=phone, email=email if is_email(email) else "", name=name,
        default_cc=casetimeline.tenant_country_code(tenant),
        source=ctx.get("channel", "chat"))
    case_id = case["id"] if case else None

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            # Serialise bookings per client so two visitors cannot take the same slot.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(tenant["id"]))
            if start_utc not in await _slots_on(tenant, start_local.date(), conn):
                return {"ok": False, "error": "Sorry, that time was just taken. Call check_availability for other times."}
            existing_lead = await conn.fetchrow('SELECT * FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], conversation_id) if conversation_id else None
            if existing_lead and case_id and not existing_lead["case_id"]:
                await conn.execute("UPDATE leads SET case_id=$2 WHERE id=$1", existing_lead["id"], case_id)
                existing_lead = dict(existing_lead, case_id=case_id)
            lead = existing_lead or await conn.fetchrow(
                """
                INSERT INTO leads (tenant_id, conversation_id, name, email, phone, message, channel,
                                   page_url, utm, webhook_status, status, consent_contact, case_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, 'booked', $11, $12)
                RETURNING *
                """,
                tenant["id"], conversation_id, name, email if is_email(email) else "", phone,
                f"Booked appointment for {automation.fmt_local(tenant, start_utc)}. {notes}".strip(),
                ctx.get("channel", "chat"), ctx.get("page_url"), json.dumps(ctx.get("utm") or {}),
                "pending" if tenant.get("lead_webhook_url") else "none", consent, case_id,
            )
            appt = await conn.fetchrow(
                """
                INSERT INTO appointments (tenant_id, lead_id, conversation_id, starts_at, ends_at, name,
                                          phone, email, notes, consent_contact, calendar_sync_requested)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true)
                RETURNING *
                """,
                tenant["id"], lead["id"], conversation_id, start_utc, end_utc, name, phone,
                email if is_email(email) else "", notes, consent,
            )
    if conversation_id:
        await convo.set_pending_booking(conversation_id, None)

    # The appointment belongs on the customer's history, or Contacts shows a booked customer with
    # no record of why they are known — the exact gap the CRM audit exists to catch.
    if case and appt:
        try:
            await casetimeline.record(
                tenant["id"], case_key=case["case_key"], channel=ctx.get("channel", "chat"),
                direction="inbound", source_key=f"appointment:{appt['id']}",
                body=f"Booked an appointment for {automation.fmt_local(tenant, start_utc)}."
                     + (f" {notes}" if notes else ""))
        except Exception:  # noqa: BLE001 - a history write must never lose a confirmed booking
            log.exception("could not record booking on the customer timeline")

    await calendar_connection.sync_one(appt['id'])
    appt = await db.pool().fetchrow('SELECT * FROM appointments WHERE tenant_id=$1 AND id=$2', tenant['id'], appt['id'])
    await calendar_connection.notify_synced(appt["id"])
    result = booking_result(tenant, appt)
    text = result['confirmation']
    ctx["appointment_text"] = text
    ctx["lead_captured"] = True
    return result


def booking_result(tenant, appt, duplicate=False):
    synced = appt.get('calendar_state') == 'synced'
    when = automation.fmt_local(tenant, appt['starts_at'])
    confirmation = (f"Booked for {when}. The calendar provider accepted the event and invitation request."
                    if synced else f"Appointment request saved for {when}. Calendar booking and invitation are pending; the team must confirm.")
    return {'ok': True, 'confirmation': confirmation, 'appointment_id': str(appt['id']),
            'booking_status': 'booked' if synced else 'pending_calendar',
            'calendar_state': appt.get('calendar_state', 'unconnected'),
            'invitation_state': appt.get('invitation_state', 'pending'), 'duplicate': duplicate}
