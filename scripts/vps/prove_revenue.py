"""One-off live proof for competitor-gap item F (attributed revenue).

Seeds two enquiries and two quotations (one accepted and paid, one accepted and unpaid), reads the
report through the real code path, verifies the money numbers, then removes every fixture.
"""
import asyncio
import json

from app import db, quote_payments, revenue

MARK = "proof-item-f"


async def main():
    await db.init()
    tenant = dict(await db.pool().fetchrow(
        "SELECT * FROM tenants WHERE slug = 'pukeko-construction'"))
    tid = tenant["id"]

    await db.pool().execute("DELETE FROM quotations WHERE tenant_id = $1 AND title LIKE $2",
                            tid, "Proof F%")
    await db.pool().execute("DELETE FROM leads WHERE tenant_id = $1 AND source_key LIKE $2",
                            tid, MARK + "%")

    ids = {}
    for channel, key, value, paid in (("phone", "paid", 120000, True),
                                      ("email", "unpaid", 80000, False)):
        lead_id = await db.pool().fetchval(
            """INSERT INTO leads(tenant_id, email, phone, message, channel, source_key)
               VALUES($1,$2,$3,$4,$5,$6) RETURNING id""",
            tid, f"{key}@example.test", "+64210000009",
            "Proof enquiry for revenue reporting", channel, f"{MARK}-{key}")
        quote_id = await db.pool().fetchval(
            """INSERT INTO quotations(tenant_id, lead_id, title, currency, status, lines, contact,
                                      tax_basis_points, subtotal_cents, tax_cents, total_cents,
                                      sent_at, public_token)
               VALUES($1,$2,$3,'NZD','accepted',$4::jsonb,$5::jsonb,1500,$6,0,$6,now(),
                      $7) RETURNING id""",
            tid, lead_id, f"Proof F {key}",
            json.dumps([{"description": "Work", "quantity": 1, "unit_price_cents": value,
                         "amount_cents": value}]),
            json.dumps({"name": "Proof"}), value, f"{MARK}-{key}")
        ids[key] = (lead_id, quote_id)
        if paid:
            row = await db.pool().fetchrow("SELECT * FROM quotations WHERE id=$1", quote_id)
            quote = dict(row)
            await quote_payments.declare(quote, reference="PROOF-F")
            await quote_payments.confirm(quote, by="owner@proof")

    report = await revenue.report(tid, 30)
    print("enquiries:", report["enquiries"], "| change vs previous:",
          report["enquiries_change_percent"])
    print("by channel:", {k: v["enquiries"] for k, v in report["by_channel"].items()})
    print("quotes sent:", report["quotes_sent"], "| accepted:", report["quotes_accepted"],
          "| accept rate:", report["accept_rate_percent"], "%")
    print("accepted value:", report["accepted_value"], report["currency"],
          "| paid:", report["paid_value"], "| outstanding:", report["outstanding_value"])
    print("value per enquiry:", report["value_per_enquiry"])
    events = await db.pool().fetch(
        """SELECT kind, amount_cents FROM quote_payments
           WHERE tenant_id = $1 AND quotation_id = $2 ORDER BY id""",
        tid, ids["paid"][1])
    print("payment trail for the paid quote:", [dict(e) for e in events])

    for lead_id, quote_id in ids.values():
        await db.pool().execute("DELETE FROM quotations WHERE id = $1", quote_id)
        await db.pool().execute("DELETE FROM leads WHERE id = $1", lead_id)
    left = await db.pool().fetchval(
        "SELECT count(*) FROM quotations WHERE tenant_id = $1 AND title LIKE $2",
        tid, "Proof F%")
    print("cleaned, quotations left:", left)
    after = await revenue.report(tid, 30)
    print("report after cleanup - enquiries:", after["enquiries"],
          "| paid:", after["paid_value"])
    await db.close()


asyncio.run(main())
