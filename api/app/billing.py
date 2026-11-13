"""The business details that make a quotation a document rather than a number on a screen.

A New Zealand quote has to say who issued it, their GST number when they are registered, a reference
the customer can quote back, and how long the price holds. None of that existed: a quote was a title,
some lines and a total. This module owns those facts and the reference counter, so every document the
product produces says the same thing.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import db

DEFAULT_VALID_DAYS = 30


def format_reference(prefix: str, number: int) -> str:
    """`Q-0001`. Sortable, unique per business, and short enough to read down a phone line."""
    clean = "".join(ch for ch in (prefix or "Q").upper() if ch.isalnum())[:4] or "Q"
    return f"{clean}-{int(number):04d}"


async def next_reference(tenant_id) -> str:
    """Claim the next reference for a business. Atomic: two quotes never share a number."""
    row = await db.pool().fetchrow(
        "UPDATE tenants SET quote_sequence = quote_sequence + 1 WHERE id=$1 "
        "RETURNING quote_sequence, upper(left(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g'), 1)) AS initial",
        tenant_id)
    if not row:
        raise ValueError("No such business")
    return format_reference(row["initial"] or "Q", row["quote_sequence"])


def valid_until(tenant: dict, created: date | None = None) -> date:
    raw = (tenant or {}).get("quote_valid_days")
    days = DEFAULT_VALID_DAYS if raw is None else int(raw)
    days = max(1, min(365, days))
    return (created or date.today()) + timedelta(days=days)


def details(tenant: dict | None) -> dict:
    """What to print in the header of every quote: who this is from, and their tax identity."""
    tenant = tenant or {}
    return {
        "name": (tenant.get("name") or "").strip(),
        "address": (tenant.get("business_address") or "").strip(),
        "phone": (tenant.get("business_phone") or "").strip(),
        "gst_number": (tenant.get("gst_number") or "").strip(),
        "nzbn": (tenant.get("nzbn") or "").strip(),
        "terms": (tenant.get("quote_terms") or "").strip(),
    }


def is_expired(valid_until_value, today: date | None = None) -> bool:
    """A quote past its date cannot be accepted — the price may no longer hold."""
    if not valid_until_value:
        return False
    today = today or date.today()
    return today > valid_until_value
