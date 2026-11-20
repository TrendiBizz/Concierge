"""The one end-of-call alert an owner gets: AI summary, full two-sided transcript, recording link.

An owner who cannot hear (tenant `owner_text_only`) acts on writing alone, so the alert has to stand
by itself: what the caller wants first, then every turn in order with both speakers labelled.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .speech_text import clean_speech, strip_control_tags

SMS_PART = 1400
SMS_MAX_PARTS = 10
CRM_NOTE = "The complete enquiry is saved in your Concierge CRM."


def turns_from(rows) -> list[tuple[str, str]]:
    """(role, text) for every spoken turn, internal markup removed, empty turns dropped."""
    out = []
    for row in rows:
        text = strip_control_tags(row["content"]).strip()
        if text and row["role"] in ("user", "assistant"):
            out.append((row["role"], text))
    return out


def caller_text(turns) -> str:
    return "\n".join(c for c in (clean_speech(t) for r, t in turns if r == "user") if c)


def transcript_block(turns) -> str:
    return "\n".join(("Caller: " if r == "user" else "Receptionist: ") + t for r, t in turns)


def fallback_summary(lead: dict, text: str) -> dict:
    """Deterministic summary from captured fields, used whenever the model gave nothing."""
    who = lead.get("name") or "A caller"
    reach = ", ".join(x for x in (lead.get("phone"), lead.get("email")) if x)
    summary = f"{who} called. They said: {text[-600:]}"
    if reach:
        summary += f" Contact: {reach}."
    return {"summary": summary, "next_step": "Contact the caller."}


def details_line(lead: dict) -> str:
    parts = [f"{k}: {lead[v]}" for k, v in (("Name", "name"), ("Phone", "phone"), ("Email", "email"))
             if lead.get(v)]
    return " | ".join(parts)


def conversation_alert(tenant: dict, insight: dict, lead: dict, turns, tail: str) -> tuple[str, str]:
    body = "Summary: " + insight["summary"]
    if insight.get("next_step"):
        body += "\nNext step: " + insight["next_step"]
    details = details_line(lead)
    if details:
        body += "\nDetails captured: " + details
    body += "\n\nFull transcript:\n" + transcript_block(turns) + tail
    return "Phone message for " + tenant["name"], body


def missed_alert(tenant: dict, number: str, started) -> tuple[str, str]:
    when = ""
    if isinstance(started, datetime):
        try:
            started = started.astimezone(ZoneInfo(tenant.get("timezone") or "UTC"))
        except Exception:
            pass
        when = " at " + started.strftime("%-d %b %H:%M")
    return ("Missed call for " + tenant["name"],
            f"Missed call from {number}{when}, no message left.\n\n{CRM_NOTE}")


def sms_parts(tenant_name: str, body: str) -> list[str]:
    """Same content as the email, split on line breaks into consecutive texts; summary comes first."""
    text = f"{tenant_name} - new phone message:\n{body}"
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > SMS_PART:
            cut = line.rfind(" ", 0, SMS_PART)
            cut = cut if cut > 0 else SMS_PART
            line, rest = line[:cut], line[cut:].lstrip()
            if current:
                chunks.append(current)
            current = ""
            chunks.append(line)
            line = rest
        if current and len(current) + 1 + len(line) > SMS_PART:
            chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    if len(chunks) > SMS_MAX_PARTS:
        chunks = chunks[:SMS_MAX_PARTS - 2] + [
            "(Middle of the transcript is in your email and Concierge CRM.)"] + chunks[-1:]
    if len(chunks) > 1:
        chunks = [f"({i}/{len(chunks)}) {c}" for i, c in enumerate(chunks, 1)]
    return chunks
