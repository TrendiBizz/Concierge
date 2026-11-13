"""Bills: what a business sends once the customer has accepted.

A quotation says what the work costs if they go ahead. An invoice says what is now owed, by when,
and for what — a tax invoice in New Zealand terms, carrying the same issuer block as the quote.

There is no card processor behind this. An owner takes payment however they already do (bank
transfer, their own link), records it against the quote, and the invoice says what is outstanding.
That is deliberate: nothing here depends on a paid service, and the schema records amounts and dates,
not card data, so a processor can be added later without throwing any of this away.
"""

from __future__ import annotations

import secrets
from datetime import date, timedelta

from . import db

KINDS = ("full", "deposit")


def split(total_cents: int, kind: str, deposit_percent: int) -> dict:
    """What is due now, and what waits for completion.

    `deposit` takes a percentage of the whole job as the first invoice and bills the rest later; a
    rounded-to-the-cent split, so the two invoices always add back to the total exactly.
    """
    total = max(0, int(total_cents))
    if kind != "deposit":
        return {"kind": "full", "due": total, "deposit": 0, "balance": 0}
    percent = max(0, min(100, int(deposit_percent)))
    # Integer half-up: Python's round() is banker's rounding, which can lose a cent
    # in a way a customer would notice on a deposit invoice.
    deposit = (total * percent + 50) // 100
    return {"kind": "deposit", "due": deposit, "deposit": deposit, "balance": total - deposit}


def format_number(prefix: str, number: int) -> str:
    clean = "".join(ch for ch in (prefix or "INV").upper() if ch.isalnum())[:3] or "INV"
    return f"{clean}-{int(number):04d}"


async def next_number(tenant_id) -> str:
    """Atomic: two invoices never share a number."""
    row = await db.pool().fetchrow(
        "UPDATE tenants SET invoice_sequence = invoice_sequence + 1 WHERE id=$1 "
        "RETURNING invoice_sequence, upper(left(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g'), 1)) AS initial",
        tenant_id)
    if not row:
        raise ValueError("No such business")
    return format_number(row["initial"] or "INV", row["invoice_sequence"])


async def issue(quote: dict, tenant: dict, kind: str) -> dict:
    """Create the invoice for an accepted quotation and return it."""
    totals = split(quote["total_cents"], kind, tenant.get("deposit_percent") or 50)
    number = await next_number(tenant["id"])
    terms = int(tenant.get("invoice_payment_terms_days") or 7)
    issued = date.today()
    token = secrets.token_urlsafe(24)
    row = await db.pool().fetchrow(
        "INSERT INTO invoices(tenant_id,quotation_id,number,kind,subtotal_cents,tax_cents,"
        "total_cents,due_cents,deposit_cents,balance_cents,currency,lines,notes,issued_on,due_on,"
        "public_token) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,$15,$16) "
        "RETURNING *",
        tenant["id"], quote["id"], number, totals["kind"], quote["subtotal_cents"],
        quote["tax_cents"], quote["total_cents"], totals["due"], totals["deposit"],
        totals["balance"], quote.get("currency") or "NZD", _json(quote.get("lines") or []),
        (quote.get("notes") or ""), issued, issued + timedelta(days=terms), token)
    return dict(row)


def _json(value):
    import json
    return json.dumps(value)


def describe(invoice: dict) -> str:
    """One line for the owner: what is owed and whether it is a stage payment."""
    if invoice["kind"] == "deposit":
        return (f"{invoice['number']}: deposit {invoice['due_cents'] / 100:,.2f} "
                f"{invoice['currency']}, balance {invoice['balance_cents'] / 100:,.2f} on completion")
    return f"{invoice['number']}: {invoice['due_cents'] / 100:,.2f} {invoice['currency']}"


# ---------------------------------------------------------------- rendering and endpoints

import html  # noqa: E402

from fastapi import APIRouter, Depends, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

from . import billing, owner_auth  # noqa: E402

public_router = APIRouter(prefix="/invoice", tags=["invoices"])
router = APIRouter(prefix="/owner/invoices", tags=["invoices"])


def _cash(cents: int, currency: str) -> str:
    return f"{int(cents) / 100:,.2f} {currency}"


async def page(token: str) -> HTMLResponse:
    """The invoice the customer receives: what is owed now, by when, and who issued it."""
    row = await db.pool().fetchrow("SELECT * FROM invoices WHERE public_token=$1", token)
    if not row:
        raise HTTPException(404, "Invoice not found")
    invoice = dict(row)
    tenant = await db.pool().fetchrow(
        "SELECT name,gst_number,nzbn,business_address,business_phone FROM tenants "
        "WHERE id=$1", invoice["tenant_id"])
    issuer = billing.details(dict(tenant) if tenant else {})
    brand = await db.pool().fetchrow(
        "SELECT name,accent,contact,logo_data FROM media_brand WHERE tenant_id=$1", invoice["tenant_id"])
    brand = dict(brand) if brand else {}
    name = html.escape(brand.get("name") or issuer["name"] or "Invoice")
    accent = html.escape(brand.get("accent") or "#c8f560")
    logo = brand.get("logo_data") or ""
    logo_tag = f'<img src="{logo}" alt="" style="height:56px">' if logo.startswith("data:image/") else ""
    contact = html.escape(brand.get("contact") or issuer["phone"] or "")
    issuer_lines = [issuer["name"]] + [value for value in (
        issuer["address"], issuer["phone"],
        ("GST " + issuer["gst_number"]) if issuer["gst_number"] else "",
        ("NZBN " + issuer["nzbn"]) if issuer["nzbn"] else "") if value]
    currency = invoice["currency"]
    lines = "".join(
        f"<tr><td>{html.escape(str(line.get('description', '')))}</td>"
        f"<td class='num'>{line.get('quantity', '')}</td>"
        f"<td class='num'>{_cash(line.get('unit_price_cents', 0), currency)}</td>"
        f"<td class='num'>{_cash(line.get('amount_cents', 0), currency)}</td></tr>"
        for line in (invoice["lines"] or []))
    stage = ""
    if invoice["kind"] == "deposit":
        stage = (f"<p><strong>Deposit invoice.</strong> {_cash(invoice['balance_cents'], currency)} remains "
                 f"due on completion, invoiced separately.</p>")
    due = invoice["due_on"].strftime("%d %b %Y") if invoice["due_on"] else ""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noai, noimageai"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice {html.escape(invoice['number'])} — {name}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;color:#15191f;background:#f6f8fa}}
.page{{max-width:820px;margin:32px auto;background:#fff;padding:40px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.08)}}
header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:6px solid {accent};padding-bottom:20px}}
h1{{margin:8px 0 4px;font-size:28px}} .muted{{color:#5a6673}}
table{{width:100%;border-collapse:collapse;margin-top:28px}}
th,td{{text-align:left;padding:10px 8px;border-bottom:1px solid #e3e7ec}}
th{{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#5a6673}}
.num{{text-align:right}} .totals{{margin-left:auto;margin-top:18px;width:340px}} .totals td{{border:0;padding:6px 8px}}
.grand{{font-weight:700;font-size:20px;border-top:2px solid {accent}}}
</style></head><body><div class="page">
<header><div>{logo_tag}<h1>Invoice</h1><p class="muted">{name}{(' · ' + contact) if contact else ''}</p></div>
<div class="muted">{html.escape(invoice['number'])}<br>{invoice['issued_on']:%d %b %Y}{('<br>Due ' + due) if due else ''}</div></header>
<p class="muted" style="font-size:13px">{'<br>'.join(html.escape(part) for part in issuer_lines)}</p>
{stage}
<table><thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead>
<tbody>{lines}</tbody></table>
<table class="totals">
<tr><td>Subtotal</td><td class="num">{_cash(invoice['subtotal_cents'], currency)}</td></tr>
<tr><td>GST</td><td class="num">{_cash(invoice['tax_cents'], currency)}</td></tr>
<tr><td>Total</td><td class="num">{_cash(invoice['total_cents'], currency)}</td></tr>
<tr class="grand"><td>Due now</td><td class="num">{_cash(invoice['due_cents'], currency)}</td></tr>
</table>
{('<p><strong>Notes</strong><br>' + html.escape(invoice['notes']).replace(chr(10), '<br>') + '</p>') if invoice['notes'] else ''}
</div></body></html>"""
    return HTMLResponse(document)


@public_router.get("/{token}", response_class=HTMLResponse)
async def public_invoice(token: str):
    return await page(token)


@router.get("")
async def list_invoices(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id,number,kind,status,due_cents,balance_cents,currency,issued_on,due_on,quotation_id,"
        "public_token FROM invoices WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200",
        user["tenant_id"])
    return [dict(row) for row in rows]
