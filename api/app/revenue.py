"""Attributed revenue: what the AI actually brought in, in money rather than counts.

Competitor-gap item F, and the number an owner renews on. GoHighLevel sells attribution because a
report that counts enquiries ("42 this month") does not answer the only question that matters:
did this pay for itself?

This reads data the product already has — `leads` (with their channel and case), `quotations`
(sent, accepted, value) and `quote_payments` (confirmed money) — and reports it per channel, with
the previous period beside it so a dip is visible without arithmetic.

Deliberately no new event pipeline: every number here is derived from rows that were written for
another reason, so the report cannot drift from the records.
"""

import logging
from datetime import datetime, timedelta, timezone

from . import db

log = logging.getLogger("concierge.revenue")

CHANNELS = ("phone", "email", "sms", "chat")


def percent_change(current: int, previous: int) -> int | None:
    """Change from the previous period, as a whole percentage. None when there is no basis."""
    if previous <= 0:
        return None if current <= 0 else 100
    return round((current - previous) / previous * 100)


def per_enquiry(cents: int, enquiries: int) -> int:
    """Average accepted value per enquiry, in cents. Zero enquiries means zero, never a crash."""
    if enquiries <= 0:
        return 0
    return int(round(cents / enquiries))


def convert_rate(numerator: int, denominator: int) -> float:
    """A percentage with one decimal, for quotes sent → accepted."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _money(cents: int) -> float:
    return round(int(cents or 0) / 100, 2)


def build(current: dict, previous: dict) -> dict:
    """Shape the API answer from two raw period summaries. Pure, so it is testable."""
    enquiries = int(current.get("enquiries") or 0)
    accepted_value = int(current.get("accepted_cents") or 0)
    prev_enquiries = int(previous.get("enquiries") or 0)
    prev_accepted_value = int(previous.get("accepted_cents") or 0)
    by_channel = {}
    for channel in CHANNELS:
        count = int((current.get("by_channel") or {}).get(channel) or 0)
        prev = int((previous.get("by_channel") or {}).get(channel) or 0)
        by_channel[channel] = {"enquiries": count, "previous": prev,
                               "change_percent": percent_change(count, prev)}
    return {
        "enquiries": enquiries,
        "enquiries_previous": prev_enquiries,
        "enquiries_change_percent": percent_change(enquiries, prev_enquiries),
        "by_channel": by_channel,
        "quotes_sent": int(current.get("quotes_sent") or 0),
        "quotes_accepted": int(current.get("quotes_accepted") or 0),
        "quotes_sent_previous": int(previous.get("quotes_sent") or 0),
        "quotes_accepted_previous": int(previous.get("quotes_accepted") or 0),
        "accept_rate_percent": convert_rate(int(current.get("quotes_accepted") or 0),
                                            int(current.get("quotes_sent") or 0)),
        "accepted_cents": accepted_value,
        "accepted_value": _money(accepted_value),
        "accepted_previous_value": _money(prev_accepted_value),
        "accepted_change_percent": percent_change(accepted_value, prev_accepted_value),
        "paid_cents": int(current.get("paid_cents") or 0),
        "paid_value": _money(current.get("paid_cents") or 0),
        "outstanding_cents": int(current.get("outstanding_cents") or 0),
        "outstanding_value": _money(current.get("outstanding_cents") or 0),
        "value_per_enquiry": _money(per_enquiry(accepted_value, enquiries)),
        "currency": current.get("currency") or "",
    }


async def _period(tenant_id, start: datetime, end: datetime) -> dict:
    """One period's raw counts, in as few round trips as the data allows."""
    leads = await db.pool().fetch(
        """SELECT channel, count(*) AS n FROM leads
           WHERE tenant_id = $1 AND created_at >= $2 AND created_at < $3
           GROUP BY channel""",
        tenant_id, start, end)
    by_channel = {row["channel"]: int(row["n"]) for row in leads}
    quotes = await db.pool().fetchrow(
        """SELECT
             count(*) FILTER (WHERE sent_at IS NOT NULL) AS quotes_sent,
             count(*) FILTER (WHERE status = 'accepted') AS quotes_accepted,
             COALESCE(SUM(total_cents) FILTER (WHERE status = 'accepted'), 0) AS accepted_cents,
             COALESCE(SUM(total_cents) FILTER (WHERE payment_confirmed_at IS NOT NULL
                                                AND payment_status = 'paid'), 0) AS paid_cents,
             COALESCE(SUM(total_cents) FILTER (WHERE status = 'accepted'
                                                AND payment_status IN ('unpaid','declared')), 0)
               AS outstanding_cents,
             max(currency) AS currency
           FROM quotations
           WHERE tenant_id = $1 AND created_at >= $2 AND created_at < $3""",
        tenant_id, start, end)
    data = dict(quotes) if quotes else {}
    data["by_channel"] = by_channel
    data["enquiries"] = sum(by_channel.values())
    return data


async def report(tenant_id, days: int = 30) -> dict:
    """This period beside the one before it. `days` is clamped so a typo cannot scan history."""
    # 0/None means "no choice given" -> the 30-day default; anything else is clamped to 1..365.
    days = max(1, min(int(days or 30), 365))
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    current = await _period(tenant_id, start, now)
    previous = await _period(tenant_id, previous_start, start)
    result = build(current, previous)
    result["days"] = days
    result["since"] = start.isoformat()
    result["note"] = (
        "Value is what the customer accepted, not what you banked; confirmed money is reported "
        "separately. Enquiries are counted when they were first captured, by channel."
    )
    return result
