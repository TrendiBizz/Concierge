"""Appointment booking: opening hours, free slots, double-booking protection, calendar invites.

Bookings live in a local SQLite file (data/concierge.db, git-ignored). A UNIQUE constraint on the
start time means two calls can never take the same slot. Settings come from environment variables
so they can change without code edits:
  BOOKING_TIMEZONE (Pacific/Auckland)  BOOKING_OPEN (09:00)  BOOKING_CLOSE (17:00)
  BOOKING_DAYS (0,1,2,3,4 = Monday to Friday)  BOOKING_SLOT_MINUTES (30)
  BOOKING_MIN_NOTICE_HOURS (2)  BOOKING_HORIZON_DAYS (14)  DATA_DIR
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("BOOKING_TIMEZONE", "Pacific/Auckland"))
_lock = threading.RLock()


class BookingError(Exception):
    """Raised when a slot cannot be booked. The message is safe to relay to the caller."""


@dataclass(frozen=True)
class Rules:
    open: time
    close: time
    days: frozenset
    slot_minutes: int
    min_notice: timedelta
    horizon_days: int


@dataclass(frozen=True)
class Appointment:
    id: str
    start: datetime
    end: datetime
    name: str
    phone: str
    email: str
    service: str
    notes: str


def rules() -> Rules:
    days = frozenset(
        int(d) for d in os.environ.get("BOOKING_DAYS", "0,1,2,3,4").split(",") if d.strip()
    )
    return Rules(
        open=time.fromisoformat(os.environ.get("BOOKING_OPEN", "09:00")),
        close=time.fromisoformat(os.environ.get("BOOKING_CLOSE", "17:00")),
        days=days,
        slot_minutes=int(os.environ.get("BOOKING_SLOT_MINUTES", "30")),
        min_notice=timedelta(hours=float(os.environ.get("BOOKING_MIN_NOTICE_HOURS", "2"))),
        horizon_days=int(os.environ.get("BOOKING_HORIZON_DAYS", "14")),
    )


def _db_path() -> Path:
    base = os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
    return Path(base) / "concierge.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE IF NOT EXISTS appointments (
            id TEXT PRIMARY KEY,
            start_utc TEXT NOT NULL UNIQUE,
            end_utc TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            service TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL)"""
    )
    return con


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def spoken(dt: datetime) -> str:
    """e.g. 'Monday 9 November at 10:30 am' in the booking timezone."""
    local = dt.astimezone(TZ)
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    return f"{local:%A} {local.day} {local:%B} at {hour}:{local.minute:02d} {suffix}"


def available_slots(day: date, now: datetime | None = None) -> list[datetime]:
    r = rules()
    now = (now or datetime.now(TZ)).astimezone(TZ)
    if day.weekday() not in r.days:
        return []
    if day > now.date() + timedelta(days=r.horizon_days):
        return []
    start = datetime.combine(day, r.open, TZ)
    end = datetime.combine(day, r.close, TZ)
    earliest = now + r.min_notice
    with _lock, closing(_connect()) as con:
        rows = con.execute(
            "SELECT start_utc FROM appointments WHERE start_utc >= ? AND start_utc < ?",
            (_utc_iso(start), _utc_iso(end)),
        ).fetchall()
    taken = {row[0] for row in rows}
    step = timedelta(minutes=r.slot_minutes)
    slots: list[datetime] = []
    t = start
    while t + step <= end:
        if t >= earliest and _utc_iso(t) not in taken:
            slots.append(t)
        t += step
    return slots


def next_available(count: int = 6, now: datetime | None = None) -> list[datetime]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    out: list[datetime] = []
    for offset in range(rules().horizon_days + 1):
        out.extend(available_slots(now.date() + timedelta(days=offset), now))
        if len(out) >= count:
            break
    return out[:count]


def book(
    start_iso: str,
    name: str,
    phone: str,
    email: str,
    service: str,
    notes: str = "",
    now: datetime | None = None,
) -> Appointment:
    try:
        start = datetime.fromisoformat(start_iso)
    except ValueError as exc:
        raise BookingError("That time was not understood.") from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ)
    start = start.astimezone(TZ)
    if not name.strip():
        raise BookingError("A name is needed to book.")
    with _lock:
        if start not in available_slots(start.date(), now):
            raise BookingError("That time is not available.")
        end = start + timedelta(minutes=rules().slot_minutes)
        appt = Appointment(
            id=uuid.uuid4().hex[:12],
            start=start,
            end=end,
            name=name.strip(),
            phone=phone,
            email=email,
            service=service.strip() or "General enquiry",
            notes=notes,
        )
        with closing(_connect()) as con:
            try:
                con.execute(
                    "INSERT INTO appointments VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        appt.id,
                        _utc_iso(appt.start),
                        _utc_iso(appt.end),
                        appt.name,
                        appt.phone,
                        appt.email,
                        appt.service,
                        appt.notes,
                        _utc_iso(datetime.now(timezone.utc)),
                    ),
                )
                con.commit()
            except sqlite3.IntegrityError as exc:
                raise BookingError("That time was just taken.") from exc
    return appt


def ics(appt: Appointment) -> str:
    """A calendar invite (.ics) the caller can add to their calendar."""

    def fmt(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Trendi//Concierge//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{appt.id}@trendibizz.com",
        f"DTSTAMP:{fmt(datetime.now(timezone.utc))}",
        f"DTSTART:{fmt(appt.start)}",
        f"DTEND:{fmt(appt.end)}",
        f"SUMMARY:Trendi consultation ({appt.service})",
        "DESCRIPTION:A Trendi team member will contact you at this time.",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
