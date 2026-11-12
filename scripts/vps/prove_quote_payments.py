"""One-off live proof for competitor-gap item E (getting paid on a quotation).

Creates a synthetic accepted quotation for a real tenant, renders the public page through the app
itself, declares and confirms payment, checks the money summary, then restores the tenant's
payment settings and deletes every fixture it created.
"""
import asyncio
import json

import httpx

from app import db, quote_payments

TOKEN = "proof-item-e-20261112"
TENANT_SLUG = "pukeko-construction"


async def main():
    await db.init()
    tenant = dict(await db.pool().fetchrow(
        "SELECT * FROM tenants WHERE slug = $1", TENANT_SLUG))
    tid = tenant["id"]
    original = (tenant["payment_instructions"], tenant["payment_url"])

    await db.pool().execute("DELETE FROM quotations WHERE public_token = $1", TOKEN)
    await db.pool().execute("DELETE FROM leads WHERE tenant_id = $1 AND source_key = $2",
                            tid, "proof-item-e")
    lead_id = await db.pool().fetchval(
        """INSERT INTO leads(tenant_id, email, phone, message, channel, source_key)
           VALUES($1, 'proof@example.test', '+64210000009',
                  'Synthetic proof of the payment step', 'chat', 'proof-item-e')
           RETURNING id""", tid)
    quote_id = await db.pool().fetchval(
        """INSERT INTO quotations(tenant_id, lead_id, title, currency, status, lines, contact,
                                  tax_basis_points, subtotal_cents, tax_cents, total_cents,
                                  public_token)
           VALUES($1,$2,'Proof: driveway','NZD','accepted',
                  $3::jsonb, $4::jsonb, 1500, 100000, 15000, 115000, $5)
           RETURNING id""",
        tid, lead_id,
        json.dumps([{"description": "Driveway", "quantity": 1, "unit_price_cents": 100000,
                     "amount_cents": 100000}]),
        json.dumps({"name": "Proof Customer"}),
        TOKEN)
    await db.pool().execute(
        "UPDATE tenants SET payment_instructions=$2, payment_url=$3 WHERE id=$1",
        tid, "Bank 12-3456-7890123-00 — use your name as the reference.", "")

    # 1. The public page must show the instructions and the declaration button.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=__import__("app.main",
                               fromlist=["app"]).app), base_url="https://proof") as client:
        page = await client.get("/quote/" + TOKEN)
    html_text = page.text
    print("public page:", page.status_code,
          "| shows instructions:", "Bank 12-3456" in html_text,
          "| shows 'I have paid':", "I have paid" in html_text,
          "| payment-declared action:", "/payment-declared" in html_text)

    # 2. Customer declares, owner confirms.
    row = await db.pool().fetchrow("SELECT * FROM quotations WHERE id=$1", quote_id)
    quote = {**dict(row)}
    declared = await quote_payments.declare(quote, reference="PROOF-REF-1")
    print("customer declares:", declared)
    row = await db.pool().fetchrow("SELECT * FROM quotations WHERE id=$1", quote_id)
    quote = {**dict(row)}
    print("state after declare:", quote["payment_status"], "| reference:", quote["payment_reference"])
    print("customer message:", quote_payments.customer_message(quote, tenant))
    confirmed = await quote_payments.confirm(quote, by="owner@proof", waive=False)
    print("owner confirms:", confirmed)

    # 3. Money summary reflects confirmed money only.
    summary = await quote_payments.summary(tid)
    print("summary:", summary)
    events = await db.pool().fetch(
        "SELECT kind, amount_cents, by_kind FROM quote_payments WHERE quotation_id=$1 "
        "ORDER BY id", quote_id)
    print("audit trail:", [dict(e) for e in events])

    # 4. A declaration is not a payment: a fresh quote cannot be confirmed twice.
    again = await quote_payments.confirm(quote, by="owner@proof")
    print("second confirm refused:", again)

    # cleanup: fixtures and the tenant's original payment settings
    await db.pool().execute(
        "UPDATE tenants SET payment_instructions=$2, payment_url=$3 WHERE id=$1",
        tid, original[0], original[1])
    await db.pool().execute("DELETE FROM quotations WHERE id=$1", quote_id)
    await db.pool().execute("DELETE FROM leads WHERE id=$1", lead_id)
    print("cleaned:", await db.pool().fetchval(
        "SELECT count(*) FROM quotations WHERE public_token=$1", TOKEN))
    await db.close()


asyncio.run(main())
