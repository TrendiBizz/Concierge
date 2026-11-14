"""Sending an owner their way in, through the product rather than by hand.

An activation email sent from a shell (`mailer.send_email(...)`) never reaches the outbox: no record
that it happened, no retry if the mail server hiccups, nothing to point at afterwards. This module
composes the invitation and queues it through the outbox, so a client's first email is as traceable
as every other message the product sends.
"""

from __future__ import annotations

import hashlib

from . import db, outbox, owner_auth
from .config import get_settings

SUBJECT = "Your Concierge account is ready"


def compose(business: str, link: str) -> tuple[str, str]:
    """The invitation a tradesman can follow without anyone on the phone.

    The copy is deliberately generic. It used to open by explaining 3D cladding takeoff as if that
    were the whole product, which tells a builder or a kitchen fitter that the thing was not built
    for them. Takeoff is a feature some businesses use, so it is offered as an aside.
    """
    body = f"""Hi,

Your Concierge account for {business} is ready.

Sign in here — no password needed, this link signs you straight in:

{link}

If the link is ever refused, ask us and we will send a fresh one. Nothing else is needed to start.

WHAT IT DOES

A chat window on your website answers customers day or night, captures their name, number and what
they want, and puts the enquiry in your inbox. From there Concierge turns it into a quote at your
own rates, a booking, and an invoice — and you approve anything before it reaches a customer.

YOUR FIRST TEN MINUTES

1. Click the sign-in link above.
2. Open "Business" and check your name, GST number and contact details.
3. Set your rates and your minimum charge, then save. These are your numbers — Concierge will never
   invent a price.
4. Open "Quotes". Anything that arrives from the chat window is here, ready to review and send.
5. Put the chat window on your website — the Setup step can have us do it for you, and there is a
   hosted chat page (with a QR code you can print) if you would rather not change the site at all.

Then everything else is in there too: enquiries, quotes, invoices, products, contacts, bookings, and
your social accounts — connect whichever you use, and nothing is published without your approval.

Any questions, just reply to this email.

Kind regards,
The Trendi Concierge team
for {business}
"""
    return SUBJECT, body


async def send(slug: str, email: str) -> dict:
    """Mint a link, queue the email, and report whether it was queued.

    Returns the invitation URL so the operator can also hand it over directly — the link works
    whether or not the email lands.
    """
    tenant = await db.pool().fetchrow("SELECT id, name FROM tenants WHERE slug=$1", slug)
    if not tenant:
        raise ValueError("No such business")
    link_info = await owner_auth.owner_link(tenant["id"], email)
    link = owner_auth.invitation_link(link_info["token"])
    origin = get_settings().owner_portal_url.rstrip("/")
    subject, body = compose(tenant["name"], link)
    # Dedupe on the LINK, not the address. Keying on the address made a re-send ("his link failed,
    # send another") return 409 "An invitation is already queued" forever, because the first
    # invitation had already used that key — so the one thing the operator needed to do was blocked.
    queued = await outbox.enqueue(tenant["id"], "owner_alert", "email", email, body,
                                  subject=subject,
                                  dedupe_key=f"owner-invite:{tenant['id']}:{hashlib.sha256(link.encode()).hexdigest()[:16]}")
    return {"invitation_url": link, "queued": queued, "email": email, "business": tenant["name"]}
