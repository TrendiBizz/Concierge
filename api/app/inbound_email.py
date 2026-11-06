"""Provider-neutral verified-email ingestion boundary.

Only an authenticated upstream adapter may call ingest_verified(). This service
does not accept public mail, send email, or invoke AI automatically. A real
provider adapter must validate that provider's native webhook authentication.
"""
import hashlib
import re
from . import db, email_drafts

MESSAGE_ID = re.compile(r"^[A-Za-z0-9._@:/+<>=-]{1,500}$")


class InboundError(ValueError):
    pass


async def ingest_verified(tenant_id, provider: str, message_id: str,
                          sender: str, recipient: str, subject: str,
                          text_body: str) -> dict:
    """Persist an untrusted email as a non-sending human-review draft.

    Tenant identity must come from a private recipient mapping, not user input.
    Caller must have authenticated the provider before reaching this function.
    """
    if provider not in ("brevo", "mailgun", "postmark", "ses", "cloudflare"):
        raise InboundError("Unsupported provider")
    if not MESSAGE_ID.fullmatch(message_id):
        raise InboundError("Invalid message identifier")
    if not recipient or len(recipient) > 320:
        raise InboundError("Invalid recipient")
    if not text_body.strip() or len(text_body) > 20000:
        raise InboundError("Invalid email body")
    if "\x00" in text_body:
        raise InboundError("Invalid email content")
    # Stable, tenant-scoped event key without storing raw provider IDs in the key.
    key = provider + ":" + hashlib.sha256(message_id.encode()).hexdigest()
    try:
        # No model call: an untrusted message must never command the assistant.
        return await email_drafts.create(
            tenant_id, sender, subject, text_body,
            "REVIEW REQUIRED — write a verified response before approval.", key,
        )
    except email_drafts.DraftError as exc:
        raise InboundError(str(exc)) from exc
