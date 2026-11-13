"""Provider-neutral verified-email ingestion boundary.

Only an authenticated upstream adapter may call ingest_verified(). This service
does not accept public mail or send email directly. Automatic replies require opt-in. A real
provider adapter must validate that provider's native webhook authentication.
"""
import hashlib
import re
from . import db, email_drafts, email_signature, enquiries, convo, flood_guard, inbound_policy, tenants

MESSAGE_ID = re.compile(r"^[A-Za-z0-9._@:/+<>=-]{1,500}$")


class InboundError(ValueError):
    pass


ACK_SENDER_WINDOW = "24 hours"


def ack_decision(tenant: dict, sender: str, subject: str, risk: str, flags: list | None,
                 auth: dict | None) -> str | None:
    """None when an acknowledgement may be queued; otherwise the reason it must not be.

    An acknowledgement is mail to whoever wrote in, so it is the one outbound path an attacker could
    point at a victim (backscatter). It therefore goes only to a sender whose DKIM signature passed
    and aligns with the From domain, never to robots or mailing lists, never for a high-risk message,
    and only when the business has switched it on.
    """
    if not tenant.get("inbound_ack"):
        return "off"
    if risk == "high":
        return "high_risk"
    if "automated_sender" in (flags or []):
        return "automated_headers"
    if flood_guard.automated_message(sender, subject):
        return "automated_address"
    if "@" not in (sender or ""):
        return "no_address"
    verified = auth or {}
    if str(verified.get("aligned", "")).lower() != "yes" and str(verified.get("dmarc", "")).lower() != "pass":
        return "sender_not_verified"
    return None


def ack_message(tenant: dict, draft_id, subject: str) -> tuple[str, str]:
    """Subject and body of the acknowledgement. The reference is the review-draft number."""
    ref = f"T-{draft_id}"
    custom = (tenant.get("inbound_ack_text") or "").strip()
    middle = custom or (
        f"Thank you for contacting {tenant.get('name') or 'us'}. We have your message and a member of our "
        "team will reply within one business day.")
    body = f"Hello,\n\n{middle}\n\nYour reference: {ref}\n\nThis is an automatic acknowledgement; there is no need to reply to it.\n"
    return f"We received your message ({ref})"[:200], body


async def queue_ack(tenant: dict, draft: dict, subject: str, key: str) -> str:
    """Queue the acknowledgement. Returns "queued" or the reason it was not. Never raises."""
    try:
        sender = draft["sender"]
        pool = db.pool()
        if await pool.fetchval(
                "SELECT 1 FROM outbox WHERE tenant_id=$1 AND kind='inbound_ack' AND lower(to_addr)=lower($2) "
                "AND created_at > now() - interval '" + ACK_SENDER_WINDOW + "' LIMIT 1", tenant["id"], sender):
            return "already_acknowledged"
        ack_subject, body = ack_message(tenant, draft["id"], subject)
        await pool.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key) "
            "VALUES($1,'inbound_ack','email',$2,$3,$4,$5) "
            "ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
            tenant["id"], sender, ack_subject, body, "ack:" + key)
        return "queued"
    except Exception:  # noqa: BLE001 - an acknowledgement must never fail the ingestion
        return "error"


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
        # The customer's own signature usually states who they are and where they work. Reading it
        # is the difference between a CRM record called "conrad@pukekoconstruction.co.nz" and one
        # called "Conrad Schiess, Pukeko Construction".
        signature = email_signature.parse_signature(text_body)
        await enquiries.capture(tenant, "email", key, subject + "\n\n" + text_body,
                                conversation_id=conversation_id, email=draft["sender"],
                                name=signature["name"], company=signature["company"],
                                phone=signature["phone"])
        detail = {"risk": risk, "flags": flags, "status": draft.get("status")}
        why_not = ack_decision(tenant, draft["sender"], subject, risk, flags, auth)
        if why_not != "off":
            detail["ack"] = why_not or await queue_ack(tenant, draft, subject, key)
        if envelope_from:
            detail["envelope_from"] = envelope_from[:320]
        await inbound_policy.audit(
            tenant_id, draft["id"], "received", "cloudflare-worker", detail)
        if tenant.get('email_auto_reply') and risk != "high" and "automated_sender" not in (flags or []):
            await db.pool().execute(
                'INSERT INTO email_secretary_jobs(tenant_id,source_key,sender,subject,body) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',
                tenant_id, key, draft['sender'], subject[:250], text_body)
        return draft
    except email_drafts.DraftError as exc:
        raise InboundError(str(exc)) from exc
