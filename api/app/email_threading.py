"""RFC 5322 threading, attachment metadata and per-tenant sender address (N10).

Pure helpers: no database, no network. Used by the inbound ingest (thread key, attachment list)
and by the outbox (In-Reply-To / References, From address).
"""
import hashlib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

MSGID = re.compile(r"<[^<>\s]{1,300}>")
SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*(\[\d+\])?\s*:\s*)+", re.I)
MAX_ATTACHMENTS = 20
MAX_REFERENCES = 20
ADDRESS = re.compile(r"^[^@\s<>\",;]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")


def normalize_subject(subject: str) -> str:
    """Subject without reply/forward prefixes, lower-cased and whitespace-collapsed."""
    text = SUBJECT_PREFIX.sub("", subject or "")
    return re.sub(r"\s+", " ", text).strip().lower()[:250]


def safe_filename(name: str) -> str:
    """A display-only file name: no path, no control characters, bounded."""
    name = re.sub(r"[\x00-\x1f\x7f]", "", name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name.strip()[:120] or "attachment"


def parse(raw: bytes | None) -> dict:
    """message_id, in_reply_to, references and attachment metadata from a raw message.

    Best effort: the Worker's copy can be truncated, so a parse failure yields empty values and
    never blocks the delivery. Attachment bytes are never kept; only name, type and size.
    """
    empty = {"message_id": "", "in_reply_to": "", "references": [], "attachments": []}
    if not raw:
        return empty
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        ids = MSGID.findall(str(msg.get("Message-ID", "")))
        reply = MSGID.findall(str(msg.get("In-Reply-To", "")))
        refs = MSGID.findall(str(msg.get("References", "")))[-MAX_REFERENCES:]
        attachments = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            disposition = (part.get_content_disposition() or "").lower()
            name = part.get_filename()
            if disposition != "attachment" and not name:
                continue
            payload = part.get_payload(decode=True) or b""
            attachments.append({
                "filename": safe_filename(name or ""),
                "content_type": (part.get_content_type() or "application/octet-stream")[:100],
                "size": len(payload),
            })
            if len(attachments) >= MAX_ATTACHMENTS:
                break
        return {"message_id": ids[0] if ids else "", "in_reply_to": reply[0] if reply else "",
                "references": refs, "attachments": attachments}
    except Exception:  # noqa: BLE001 - never let a malformed message cost the delivery
        return empty


def thread_key(sender: str, subject: str, in_reply_to: str = "", references: list | None = None) -> str:
    """Stable conversation key for one email thread.

    A reply carries the root of its thread in References (or the parent in In-Reply-To), so every
    message of one thread maps to one key; a new subject from the same sender starts a new thread
    (the old key was sha256(sender), which merged unrelated subjects).
    """
    refs = list(references or [])
    root = refs[0] if refs else (in_reply_to or "")
    basis = ("id:" + root) if root else ("subj:" + parseaddr(sender)[1].lower() + "|" + normalize_subject(subject))
    return "email" + hashlib.sha256(basis.encode()).hexdigest()[:50]


def reply_headers(parent_message_id: str, parent_references: list | None) -> dict:
    """In-Reply-To and References for a reply to a stored inbound message. Empty when unknown."""
    parent = MSGID.fullmatch((parent_message_id or "").strip())
    if not parent:
        return {}
    chain = [r for r in (parent_references or []) if MSGID.fullmatch(r)][-(MAX_REFERENCES - 1):]
    return {"In-Reply-To": parent.group(0), "References": " ".join(chain + [parent.group(0)])}


def attachment_notice(attachments: list | None) -> str:
    """One owner-facing line so attachments are never dropped silently."""
    items = attachments or []
    if not items:
        return ""
    names = ", ".join(f"{a['filename']} ({a['content_type']}, {max(1, a['size'] // 1024)} KB)" for a in items[:10])
    more = f" and {len(items) - 10} more" if len(items) > 10 else ""
    return (f"[The customer attached {len(items)} file(s): {names}{more}. Files are not stored by "
            "Concierge; ask the customer to resend them or open the original in your mailbox.]\n\n")


def sender_address(tenant: dict, default_from: str) -> str:
    """From address: the tenant's own address only after an operator verified its domain."""
    own = (tenant.get("send_from_address") or "").strip()
    if own and tenant.get("send_from_verified") and ADDRESS.fullmatch(own):
        return own
    return default_from
