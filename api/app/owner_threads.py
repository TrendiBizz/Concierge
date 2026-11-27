"""Email threads the owner runs from their own mailbox.

Concierge only sees mail coming IN. When the owner answers a customer straight from Gmail or Outlook,
nothing reaches us, so the enquiry stays 'new' and the "no reply yet" ACTION NEEDED notice nags about a
conversation the owner is already having. (27 Nov 2026: Ruben's "thanks Jo, our link is live" reply to
Jo's own outreach email raised ACTION NEEDED on 25 and 27 Nov.)

Evidence: the customer's email is a reply (In-Reply-To, else the last References id) to a message that
is NOT one of their own earlier emails we received, and Concierge has emailed them nothing in the last
30 days. The only other writer in that thread is the owner. Then:

* the customer's earlier 'new' email enquiries were answered by the owner -> 'contacted';
* this enquiry is flagged ``owner_thread`` and the "no reply yet" notice skips it. The owner still gets
  the normal enquiry alert, and the mail is in their own inbox thread.

When Concierge did email them, the parent could be ours, so nothing is inferred and the chase stays on.
"""
from . import db

LOOKBACK_DAYS = 30


def _parent(mail: dict | None) -> str:
    mail = mail or {}
    parent = (mail.get("in_reply_to") or "").strip()
    if not parent:
        refs = mail.get("references") or []
        parent = str(refs[-1]).strip() if refs else ""
    return parent


async def note(tenant_id, lead: dict | None, sender: str, mail: dict | None) -> bool:
    """Flag an owner-run thread. True when the enquiry was flagged (see module doc)."""
    parent = _parent(mail)
    address = (sender or "").strip().lower()
    if not parent or not address or not lead or not lead.get("id"):
        return False
    pool = db.pool()
    own = await pool.fetchval(
        "SELECT 1 FROM email_drafts WHERE tenant_id=$1 AND message_id_hdr=$2 LIMIT 1", tenant_id, parent)
    if own:
        return False      # replying to their own earlier email: nobody at the business has answered
    ours = await pool.fetchval(
        "SELECT 1 FROM outbox WHERE tenant_id=$1 AND channel='email' AND lower(to_addr)=$2 "
        "AND status NOT IN ('failed','held','suppressed','cancelled','skipped') AND created_at > now() - make_interval(days => $3) LIMIT 1",
        tenant_id, address, LOOKBACK_DAYS)
    if ours:
        return False      # we emailed them: the parent may be ours, so we cannot tell
    await pool.execute(
        "UPDATE leads SET status='contacted', updated_at=now() "
        "WHERE tenant_id=$1 AND channel='email' AND lower(email)=$2 AND status='new' AND id<>$3 "
        "AND created_at <= (SELECT created_at FROM leads WHERE id=$3)",
        tenant_id, address, lead["id"])
    await pool.execute("UPDATE leads SET owner_thread=true WHERE id=$1 AND tenant_id=$2", lead["id"], tenant_id)
    return True
