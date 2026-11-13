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


def compose(business: str, link: str, guide_url: str) -> tuple[str, str]:
    """The invitation a tradesman can follow without anyone on the phone."""
    body = f"""Hi,

Your Concierge account for {business} is ready.

Sign in here — no password needed, this link signs you straight in:

{link}

It is a single-use link. If it expires, ask us and we will send a fresh one.

WHAT IT DOES

You draw a house once in a free 3D program, and Concierge measures the outside clad area, subtracts
the windows and doors, adds your waste, and prices it at your rate per square metre. You review the
quote and send it.

The 3D program is free: Blender, plus a free add-on called Bonsai. Step-by-step guide:

{guide_url}

YOUR FIRST TEN MINUTES

1. Click the sign-in link above.
2. Open "Designs and CAD" (under Revenue, just below Quotes).
3. Set your rate per m2, your waste %, and your minimum charge, then press Save rates. These are your
   numbers — a quote will never invent a price.
4. Upload a model exported from Bonsai (.ifc), press "IFC takeoff", then "Price this model".
5. Open "Quotes" to review it and send it to the customer.

Then everything else is in there too: enquiries, quotes, products, contacts, bookings, and your social
accounts — connect whichever you use, and nothing is published without your approval first.

Any questions, just reply to this email.

Kind regards,
The Concierge team
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
    subject, body = compose(tenant["name"], link, f"{origin}/guide/bonsai-cladding")
    # Dedupe on the LINK, not the address. Keying on the address made a re-send ("his link failed,
    # send another") return 409 "An invitation is already queued" forever, because the first
    # invitation had already used that key — so the one thing the operator needed to do was blocked.
    queued = await outbox.enqueue(tenant["id"], "owner_alert", "email", email, body,
                                  subject=subject,
                                  dedupe_key=f"owner-invite:{tenant['id']}:{hashlib.sha256(link.encode()).hexdigest()[:16]}")
    return {"invitation_url": link, "queued": queued, "email": email, "business": tenant["name"]}
