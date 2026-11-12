"""Delivery Status Notification (bounce) parsing.

Pure functions: bytes in, a dict out. No I/O, no database, no network. The caller
decides what to do with the result (suppress the address, close the outbox row).

Why this exists: until 2026-11-12 there was no bounce handling anywhere. `outbox`
marked a row `sent` when the SMTP server accepted it, so a later hard bounce was
invisible and a dead address was retried forever. A DSN that came back to a tenant
reply address was even treated as ordinary customer mail and became a draft.
"""
import re

from email import policy
from email.parser import BytesParser

# Local parts that only ever send reports, never customer mail.
BOUNCE_SENDERS = ("mailer-daemon", "postmaster", "bounces", "mailerdaemon", "noreply-dmarc")
ADDRESS = re.compile(r"[^\s<>;:,]+@[^\s<>;:,.]+(?:\.[^\s<>;:,.]+)+")
HARD_STATUS = ("4.4", "5.")  # 5.x.x is permanent; 4.4.x is "no route" persistence
FAILURE_ACTIONS = ("failed",)
DELAY_ACTIONS = ("delayed", "delay")


def looks_like_bounce(sender: str, subject: str, content_type: str) -> bool:
    local = (sender or "").strip().lower().split("@")[0]
    if any(local.startswith(prefix) for prefix in BOUNCE_SENDERS):
        return True
    if "multipart/report" in (content_type or "").lower():
        return True
    subject_lower = (subject or "").lower()
    return "undeliver" in subject_lower or "delivery status notification" in subject_lower


def _address(value: str) -> str:
    match = ADDRESS.search(value or "")
    return match.group(0).strip(" .").lower() if match else ""


def _blocks(part) -> list:
    payload = part.get_payload()
    if isinstance(payload, list):
        return [block for block in payload if hasattr(block, "get")]
    return []


def parse(raw: bytes, max_bytes: int = 200_000) -> dict | None:
    """Return {address, status, action, diagnostic, original_message_id, hard}

    None means "not a delivery report" (or unparseable): the caller must treat the
    message as ordinary mail rather than silently dropping it.
    """
    if not raw or len(raw) > max_bytes:
        return None
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception:  # noqa: BLE001 - malformed attacker-controlled input
        return None
    report = message.get_content_type() == "multipart/report"
    if not report and message.get_content_type() != "message/delivery-status":
        return None

    records = []
    for part in message.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        for block in _blocks(part):
            final = str(block.get("Final-Recipient") or "")
            original = str(block.get("Original-Recipient") or "")
            records.append({
                "address": _address(final) or _address(original),
                "action": str(block.get("Action") or "").strip().lower(),
                "status": str(block.get("Status") or "").strip(),
                "diagnostic": " ".join(str(block.get("Diagnostic-Code") or "").split())[:300],
            })
    if not records:
        return None

    # The first failing record is the one that matters; a delay notice is not a bounce.
    failure = next((r for r in records if r["action"] in FAILURE_ACTIONS), None)
    delayed = next((r for r in records if r["action"] in DELAY_ACTIONS), None)
    chosen = failure or delayed or records[0]

    original_message_id = ""
    for part in message.walk():
        if part.get_content_type() == "message/rfc822" and isinstance(part.get_payload(), list):
            inner = part.get_payload()[0]
            if hasattr(inner, "get"):
                original_message_id = str(inner.get("Message-ID") or "").strip()
                break
    if not original_message_id:
        for header in ("X-Original-Message-ID", "In-Reply-To", "References"):
            value = str(message.get(header) or "").strip()
            if value:
                original_message_id = value.split()[-1]
                break

    status = chosen["status"]
    hard = bool(failure) and (status.startswith("5.") or status.startswith(HARD_STATUS[0]))
    # 4.4.x from a failure action means "no route to host" (permanent-ish); 4.x
    # otherwise is a transient delay and must NOT suppress the address.
    if failure and status.startswith("4.4"):
        hard = True
    return {
        "address": chosen["address"],
        "action": chosen["action"],
        "status": status,
        "diagnostic": chosen["diagnostic"],
        "original_message_id": original_message_id[:500],
        "hard": hard,
    }
