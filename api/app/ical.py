"""A calendar feed (iCalendar, RFC 5545) of a client's appointments, to subscribe to from Google, Apple or
Outlook Calendar. Read-only. The feed address contains a long random token, which is the only credential, so
it must be treated like a password. It lists customer names, phone numbers and notes for the owner's own use.
"""

from datetime import datetime, timezone

PRODID = "-//Concierge//Appointments//EN"


def esc(text: str) -> str:
    """Escape a TEXT value: backslash, semicolon, comma and line breaks."""
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """Fold a content line at 75 octets, never splitting a multi-byte character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current, limit = [], b"", 75
    for ch in line:
        piece = ch.encode("utf-8")
        if len(current) + len(piece) > limit:
            parts.append(current.decode("utf-8"))
            current, limit = b"", 74  # continuation lines start with a space
        current += piece
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build(tenant: dict, appointments: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(tenant['name'] + ' appointments')}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M", "X-PUBLISHED-TTL:PT15M",
    ]
    for a in appointments:
        description = "\n".join(x for x in (
            f"Phone: {a['phone']}" if a.get("phone") else "",
            f"Email: {a['email']}" if a.get("email") else "",
            a.get("notes") or "",
        ) if x)
        lines += [
            "BEGIN:VEVENT",
            f"UID:appt-{a['id']}@concierge",
            f"DTSTAMP:{_stamp(now)}",
            f"DTSTART:{_stamp(a['starts_at'])}",
            f"DTEND:{_stamp(a['ends_at'])}",
            f"SUMMARY:{esc((a.get('name') or 'Appointment') + ' - ' + tenant['name'])}",
            f"DESCRIPTION:{esc(description)}" if description else "",
            f"STATUS:{'CANCELLED' if a.get('status') == 'cancelled' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines if x) + "\r\n"
