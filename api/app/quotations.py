"""Tenant-private, reviewed quotation snapshots. Money uses integer minor units."""
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
import html
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db, outbox, owner_auth
from .config import get_settings
from urllib.parse import urlsplit

router = APIRouter(prefix='/owner/crm/quotations', tags=['quotations'])
public_router = APIRouter(prefix='/quote', tags=['quotations'])


class QuoteLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(gt=0, le=100000, decimal_places=3)
    unit_price_cents: int = Field(ge=0, le=100_000_000, strict=True)

    @field_validator('description')
    @classmethod
    def readable(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Enter a readable line description')
        return value.strip()


class QuoteDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lead_id: UUID
    title: str = Field(min_length=1, max_length=160)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    tax_basis_points: int = Field(default=0, ge=0, le=10000, strict=True)
    lines: list[QuoteLine] = Field(min_length=1, max_length=100)
    notes: str = Field(default='', max_length=4000)
    version: int = Field(default=1, ge=1)

    @field_validator('title')
    @classmethod
    def readable_title(cls, value):
        if not value.strip() or any(ord(c)<32 for c in value):
            raise ValueError('Enter a readable quotation title')
        return value.strip()


def calculate(draft):
    lines = []
    for line in draft.lines:
        amount = int((line.quantity * line.unit_price_cents).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        lines.append({**line.model_dump(mode='json'), 'amount_cents': amount})
    subtotal = sum(line['amount_cents'] for line in lines)
    tax = int((Decimal(subtotal) * draft.tax_basis_points / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if subtotal + tax > 100_000_000_000:
        raise HTTPException(422, 'Quotation total exceeds supported amount')
    return lines, subtotal, tax, subtotal + tax


def view(row):
    result = dict(row)
    for key in ('lines', 'contact'):
        if isinstance(result.get(key), str):
            result[key] = json.loads(result[key])
    return result


@router.get('')
async def listing(user=Depends(owner_auth.current_user)):
    rows = await db.pool().fetch('SELECT * FROM quotations WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200', user['tenant_id'])
    return [view(row) for row in rows]


@router.post('', status_code=201)
async def create(body: QuoteDraft, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'editor')
    lines, subtotal, tax, total = calculate(body)
    lead = await db.pool().fetchrow('SELECT id,name,email,phone FROM leads WHERE tenant_id=$1 AND id=$2', user['tenant_id'], body.lead_id)
    if not lead:
        raise HTTPException(404, 'Enquiry not found')
    row = await db.pool().fetchrow(
        'INSERT INTO quotations(tenant_id,lead_id,title,currency,tax_basis_points,lines,subtotal_cents,tax_cents,total_cents,notes,contact) '
        'VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11::jsonb) RETURNING *',
        user['tenant_id'], body.lead_id, body.title.strip(), body.currency, body.tax_basis_points,
        json.dumps(lines), subtotal, tax, total, body.notes, json.dumps(dict(lead), default=str))
    return view(row)


@router.put('/{quote_id}')
async def revise(quote_id: UUID, body: QuoteDraft, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'editor')
    lines, subtotal, tax, total = calculate(body)
    row = await db.pool().fetchrow(
        "UPDATE quotations SET title=$4,currency=$5,tax_basis_points=$6,lines=$7::jsonb,subtotal_cents=$8,tax_cents=$9,total_cents=$10,notes=$11,version=version+1,updated_at=now() "
        "WHERE tenant_id=$1 AND id=$2 AND version=$3 AND status='draft' AND lead_id=$12 RETURNING *",
        user['tenant_id'], quote_id, body.version, body.title.strip(), body.currency, body.tax_basis_points,
        json.dumps(lines), subtotal, tax, total, body.notes, body.lead_id)
    if not row:
        raise HTTPException(409, 'Draft unavailable or changed; refresh before editing')
    return view(row)


class QuoteStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern=r'^(reviewed|accepted|declined|void)$')
    version: int = Field(ge=1)


@router.post('/{quote_id}/status')
async def change_status(quote_id: UUID, body: QuoteStatus, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    allowed = {'reviewed': ['draft'], 'accepted': ['reviewed'], 'declined': ['reviewed'], 'void': ['draft', 'reviewed', 'accepted', 'declined']}
    row = await db.pool().fetchrow(
        'UPDATE quotations SET status=$4,version=version+1,updated_at=now() '
        'WHERE tenant_id=$1 AND id=$2 AND version=$3 AND status=ANY($5::text[]) RETURNING *',
        user['tenant_id'], quote_id, body.version, body.status, allowed[body.status])
    if not row:
        raise HTTPException(409, 'Quotation changed or transition unavailable; refresh first')
    return view(row)


@router.get('/{quote_id}/print', response_class=HTMLResponse, include_in_schema=False)
async def print_view(quote_id: UUID, user=Depends(owner_auth.current_user)):
    """Branded, print-ready quotation (browser Print → Save as PDF)."""
    row = await db.pool().fetchrow('SELECT * FROM quotations WHERE tenant_id=$1 AND id=$2', user['tenant_id'], quote_id)
    if not row:
        raise HTTPException(404, 'Quotation not found')
    quote = view(row)
    tenant = await db.pool().fetchrow('SELECT name,site_url FROM tenants WHERE id=$1', user['tenant_id'])
    brand = await db.pool().fetchrow('SELECT name,accent,contact,logo_data FROM media_brand WHERE tenant_id=$1', user['tenant_id'])
    brand = dict(brand) if brand else {}
    name = html.escape((brand.get('name') or (tenant['name'] if tenant else '') or 'Quotation'))
    accent = html.escape(brand.get('accent') or '#c8f560')
    contact = html.escape(brand.get('contact') or (tenant['site_url'] if tenant and tenant['site_url'] else '') or '')
    logo = brand.get('logo_data') or ''
    currency = quote['currency']
    def cash(cents: int) -> str:
        return f"{cents / 100:,.2f} {currency}"
    lines = ''.join(
        f"<tr><td>{html.escape(line['description'])}</td><td class='num'>{line['quantity']}</td>"
        f"<td class='num'>{cash(line['unit_price_cents'])}</td><td class='num'>{cash(line['amount_cents'])}</td></tr>"
        for line in quote['lines'])
    logo_tag = f'<img src="{logo}" alt="" style="height:64px">' if logo.startswith('data:image/') else ''
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{html.escape(quote['title'])} — {name}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;color:#15191f}}
.page{{max-width:820px;margin:0 auto;padding:40px}}
header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:6px solid {accent};padding-bottom:20px}}
h1{{margin:8px 0 4px;font-size:28px}} .muted{{color:#5a6673}} table{{width:100%;border-collapse:collapse;margin-top:28px}}
th,td{{text-align:left;padding:10px 8px;border-bottom:1px solid #e3e7ec}} th{{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#5a6673}}
.num{{text-align:right}} .totals{{margin-left:auto;margin-top:18px;width:320px}} .totals td{{border:0;padding:6px 8px}}
.grand{{font-weight:700;font-size:20px;border-top:2px solid {accent}}} footer{{margin-top:36px;font-size:13px;color:#5a6673}}
.status{{display:inline-block;padding:4px 10px;border-radius:999px;background:{accent};color:#101408;font-size:12px;font-weight:700;text-transform:uppercase}}
@media print{{.page{{padding:0}} .no-print{{display:none}}}}
</style></head><body><div class="page">
<header><div>{logo_tag}<h1>{html.escape(quote['title'])}</h1><p class="muted">{name}{(' · ' + contact) if contact else ''}</p></div>
<div><span class="status">{html.escape(quote['status'])}</span><p class="muted">{quote['created_at']:%d %b %Y}<br>Version {quote['version']}</p></div></header>
<p><strong>Prepared for:</strong> {html.escape(str(quote.get('contact', {}).get('name') or quote.get('contact', {}).get('email') or 'Customer'))}</p>
<table><thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead><tbody>{lines}</tbody></table>
<table class="totals"><tr><td>Subtotal</td><td class="num">{cash(quote['subtotal_cents'])}</td></tr>
<tr><td>Tax</td><td class="num">{cash(quote['tax_cents'])}</td></tr>
<tr class="grand"><td>Total</td><td class="num">{cash(quote['total_cents'])}</td></tr></table>
{('<p><strong>Notes</strong><br>' + html.escape(quote['notes']).replace(chr(10), '<br>') + '</p>') if quote.get('notes') else ''}
<footer>{name} · Quotation {html.escape(str(quote['id']))[:8]} · Prices in {currency}. This quotation is a draft until reviewed and signed off by the business owner.</footer>
<p class="no-print"><button onclick="window.print()">Print / Save as PDF</button></p>
</div></body></html>"""
    return HTMLResponse(document)


@public_router.get('/{token}', response_class=HTMLResponse)
async def public_quote(token: str):
    row = await db.pool().fetchrow('SELECT * FROM quotations WHERE public_token=$1', token)
    if not row:
        raise HTTPException(404, 'Quotation not found')
    quote = view(row)
    tenant = await db.pool().fetchrow('SELECT id,name,site_url FROM tenants WHERE id=$1', quote['tenant_id'])
    brand = await db.pool().fetchrow('SELECT name,accent,contact,logo_data FROM media_brand WHERE tenant_id=$1', quote['tenant_id'])
    brand = dict(brand) if brand else {}
    name = html.escape(brand.get('name') or (tenant['name'] if tenant else '') or 'Quotation')
    accent = html.escape(brand.get('accent') or '#c8f560')
    contact = html.escape(brand.get('contact') or (tenant['site_url'] if tenant and tenant['site_url'] else '') or '')
    logo = brand.get('logo_data') or ''
    logo_tag = f'<img src="{logo}" alt="" style="height:56px">' if logo.startswith('data:image/') else ''
    currency = quote['currency']
    cash = lambda cents: f"{cents / 100:,.2f} {currency}"
    lines = ''.join(
        f"<tr><td>{html.escape(line['description'])}</td><td class='num'>{line['quantity']}</td>"
        f"<td class='num'>{cash(line['unit_price_cents'])}</td><td class='num'>{cash(line['amount_cents'])}</td></tr>"
        for line in quote['lines'])
    status = quote['status']
    if status == 'reviewed':
        actions = f"""<form method="post" action="/quote/{html.escape(token)}/accept" style="display:inline">
<button type="submit" style="background:{accent};color:#101408;border:0;padding:14px 22px;border-radius:999px;font-weight:700;cursor:pointer">Accept quotation</button></form>
<form method="post" action="/quote/{html.escape(token)}/decline" style="display:inline;margin-left:8px">
<button type="submit" style="background:transparent;border:1px solid #c9d1da;padding:14px 22px;border-radius:999px;font-weight:700;cursor:pointer">Decline</button></form>"""
        note = 'This quotation was reviewed and signed off by the business owner.'
    elif status in ('accepted', 'declined'):
        actions = f"<p><strong>This quotation has been {html.escape(status)}.</strong></p>"
        note = ''
    else:
        actions = '<p>This quotation is not ready for acceptance yet.</p>'
        note = 'The business owner still needs to review it.'
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow, noai, noimageai"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(quote['title'])} — {name}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;color:#15191f;background:#f6f8fa}}
.page{{max-width:820px;margin:32px auto;background:#fff;padding:40px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.08)}}
header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:6px solid {accent};padding-bottom:20px}}
h1{{margin:8px 0 4px;font-size:28px}} .muted{{color:#5a6673}} table{{width:100%;border-collapse:collapse;margin-top:28px}}
th,td{{text-align:left;padding:10px 8px;border-bottom:1px solid #e3e7ec}} th{{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#5a6673}}
.num{{text-align:right}} .totals{{margin-left:auto;margin-top:18px;width:320px}} .totals td{{border:0;padding:6px 8px}}
.grand{{font-weight:700;font-size:20px;border-top:2px solid {accent}}} .actions{{margin-top:32px;padding-top:24px;border-top:1px solid #e3e7ec}}
</style></head><body><div class="page">
<header><div>{logo_tag}<h1>{html.escape(quote['title'])}</h1><p class="muted">{name}{(' · ' + contact) if contact else ''}</p></div>
<div class="muted">{quote['created_at']:%d %b %Y}<br>Version {quote['version']}</div></header>
<p><strong>Prepared for:</strong> {html.escape(str(quote.get('contact', {}).get('name') or quote.get('contact', {}).get('email') or 'Customer'))}</p>
<table><thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead><tbody>{lines}</tbody></table>
<table class="totals"><tr><td>Subtotal</td><td class="num">{cash(quote['subtotal_cents'])}</td></tr>
<tr><td>Tax</td><td class="num">{cash(quote['tax_cents'])}</td></tr>
<tr class="grand"><td>Total</td><td class="num">{cash(quote['total_cents'])}</td></tr></table>
{('<p><strong>Notes</strong><br>' + html.escape(quote['notes']).replace(chr(10), '<br>') + '</p>') if quote.get('notes') else ''}
<div class="actions">{actions}<p class="muted">{html.escape(note)}</p></div>
</div></body></html>"""
    return HTMLResponse(document)


async def _decide(token: str, status: str):
    row = await db.pool().fetchrow('SELECT id,status FROM quotations WHERE public_token=$1', token)
    if not row:
        raise HTTPException(404, 'Quotation not found')
    if row['status'] != 'reviewed':
        raise HTTPException(409, 'This quotation is no longer available')
    column = 'accepted_at' if status == 'accepted' else 'declined_at'
    await db.pool().execute(
        f'UPDATE quotations SET status=$2, {column}=now(), version=version+1, updated_at=now() WHERE id=$1',
        row['id'], status)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow, noai, noimageai"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Quotation {status}</title></head>
<body style="font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:24px"><h1>Quotation {status}</h1><p>Thank you. The business has been notified.</p></body></html>""")


@public_router.post('/{token}/accept')
async def public_accept(token: str):
    return await _decide(token, 'accepted')


@public_router.post('/{token}/decline')
async def public_decline(token: str):
    return await _decide(token, 'declined')


@router.post('/{quote_id}/send')
async def send_quote(quote_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    row = await db.pool().fetchrow('SELECT * FROM quotations WHERE tenant_id=$1 AND id=$2', user['tenant_id'], quote_id)
    if not row:
        raise HTTPException(404, 'Quotation not found')
    quote = view(row)
    if quote['status'] != 'reviewed':
        raise HTTPException(409, 'Only a reviewed quotation can be sent')
    contact = quote.get('contact') or {}
    email = (contact.get('email') or '').strip()
    if not email:
        raise HTTPException(422, 'This enquiry has no email address; add one before sending')
    tenant = await db.pool().fetchrow('SELECT name FROM tenants WHERE id=$1', user['tenant_id'])
    origin = urlsplit(get_settings().owner_portal_url)
    link = f"{origin.scheme}://{origin.netloc}/quote/" + quote['public_token']
    body = f"Kia ora,\n\n{tenant['name']} has prepared a quotation: {quote['title']}.\n\n{link}\n\nYou can review and accept or decline it online.\n\nThank you."
    await outbox.enqueue(user['tenant_id'], 'quotation', 'email', email, body,
                         subject=f"Quotation: {quote['title']}",
                         lead_id=quote['lead_id'],
                         dedupe_key=f"quote:{quote['id']}:{quote['version']}")
    await db.pool().execute('UPDATE quotations SET sent_at=now() WHERE id=$1', quote['id'])
    return {'link': link, 'sent_to': email}
