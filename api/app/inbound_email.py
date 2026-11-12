"""Provider-neutral verified-email ingestion boundary.

Only an authenticated upstream adapter may call ingest_verified(). This service
does not accept public mail or send email directly. Automatic replies require opt-in. A real
provider adapter must validate that provider's native webhook authentication.
"""
import hashlib
import re
from . import db, email_drafts, enquiries, convo, inbound_policy, tenants

MESSAGE_ID = re.compile(r"^[A-Za-z0-9._@:/+<>=-]{1,500}$")


class InboundError(ValueError):
    pass


async def ingest_verified(tenant_id, provider: str, message_id: str,
                          sender: str, recipient: str, subject: str,
                          text_body: str, auth: dict | None = None,
                          risk: str = "low", flags: list | None = None,
                          envelope_from: str | None = None) -> dict:
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
        # High-risk messages are quarantined until a human releases them.
        draft = await email_drafts.create(
            tenant_id, sender, subject, text_body,
            "REVIEW REQUIRED — write a verified response before approval.", key,
            auth=auth, risk=risk, flags=flags,
            status="quarantined" if risk == "high" else "draft",
            recipient=recipient,
        )
        tenant = await tenants.get_by_id(tenant_id)
        conversation_id = await convo.get_or_create(tenant, "email" + hashlib.sha256(draft["sender"].lower().encode()).hexdigest()[:50], "email", None, None)
        await enquiries.capture(tenant, "email", key, subject + "\n\n" + text_body,
                                conversation_id=conversation_id, email=draft["sender"])
        detail = {"risk": risk, "flags": flags, "status": draft.get("status")}
        if envelope_from:
            detail["envelope_from"] = envelope_from[:320]
        await inbound_policy.audit(
            tenant_id, draft["id"], "received", "cloudflare-worker", detail)
        if tenant.get('email_auto_reply') and risk != "high":
            await db.pool().execute(
                'INSERT INTO email_secretary_jobs(tenant_id,source_key,sender,subject,body) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',
                tenant_id, key, draft['sender'], subject[:250], text_body)
        return draft
    except email_drafts.DraftError as exc:
        raise InboundError(str(exc)) from exc
