"""Tenant-private, reviewed quotation snapshots. Money uses integer minor units."""
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db, owner_auth

router = APIRouter(prefix='/owner/crm/quotations', tags=['quotations'])


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
