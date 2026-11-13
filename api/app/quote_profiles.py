"""Quoting methods: how many square metres become a price.

A trades business does not price by catalogue row when the work is measured off a drawing. A cladding
contractor quotes the outside clad area at a rate per square metre, adds waste, and has a minimum
callout. Another customer prices per hour or at a fixed price. Each is a profile stored here; the
arithmetic lives in `compute_quote` so it can be tested without a database or a browser.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import db, owner_auth

router = APIRouter(prefix='/owner/quote-profiles', tags=['quote profiles'])

MEASUREMENT_LABEL = {
    'net_cladding': 'outside clad area net of openings',
    'net_wall': 'wall area net of openings',
    'gross_wall': 'gross wall area',
}


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default='m²', min_length=1, max_length=16)
    rate_cents: int = Field(default=0, ge=0, le=100_000_000, strict=True)
    waste_percent: Decimal = Field(default=Decimal('0'), ge=0, le=100, decimal_places=2)
    minimum_cents: int = Field(default=0, ge=0, le=100_000_000, strict=True)
    measurement: str = Field(default='net_cladding', pattern='^(net_cladding|net_wall|gross_wall)$')
    currency: str = Field(default='NZD', pattern=r'^[A-Z]{3}$')
    tax_basis_points: int = Field(default=1500, ge=0, le=10000, strict=True)
    is_default: bool = True
    active: bool = True
    notes: str = Field(default='', max_length=2000)


def _money(cents: int) -> str:
    return '$%.2f' % (cents / 100)


def compute_quote(profile: dict, takeoff: dict) -> dict:
    """Turn a measured takeoff into one priced line. Pure: no database, no rounding surprises.

    Returns the line, the measured area used, and notes for anything the owner should see (waste
    added, minimum charge applied). Refuses rather than inventing an area.
    """
    measurement = profile.get('measurement') or 'net_cladding'
    source_key = {'net_cladding': 'net_cladding_area_m2', 'net_wall': 'net_wall_area_m2',
                  'gross_wall': 'gross_wall_area_m2'}[measurement]
    raw = takeoff.get(source_key) if isinstance(takeoff, dict) else None
    if not isinstance(raw, (int, float)) or float(raw) <= 0:
        raise ValueError('This model has no usable %s, so there is nothing to price.'
                         % MEASUREMENT_LABEL[measurement])
    area = Decimal(str(raw)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    waste = Decimal(str(profile.get('waste_percent') or 0))
    billed_area = (area * (1 + waste / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    rate = int(profile.get('rate_cents') or 0)
    amount = int((billed_area * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    minimum = int(profile.get('minimum_cents') or 0)
    notes: list[str] = []
    if waste > 0:
        notes.append('%s%% waste added to the measured area (%s %s measured).'
                     % (waste.normalize(), area, profile.get('unit') or 'm²'))
    if minimum and amount < minimum:
        notes.append('Minimum charge of %s applied (measured %s came to %s).'
                     % (_money(minimum), billed_area, _money(amount)))
        amount = minimum
    description = '%s — %s %s at %s/%s' % (
        profile.get('name') or 'Measured work',
        billed_area,
        profile.get('unit') or 'm²',
        _money(rate),
        profile.get('unit') or 'm²',
    )
    return {
        'line': {'description': description[:300], 'quantity': str(billed_area),
                 'unit_price_cents': rate, 'amount_cents': amount},
        'measured_area': str(area),
        'billed_area': str(billed_area),
        'amount_cents': amount,
        'notes': notes,
    }


def view(row) -> dict:
    result = dict(row)
    for key in ('waste_percent',):
        if key in result and result[key] is not None:
            result[key] = str(result[key])
    return result


@router.get('')
async def listing(user=Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        'SELECT * FROM quote_profiles WHERE tenant_id=$1 AND active ORDER BY is_default DESC, name',
        user['tenant_id'])
    return [view(row) for row in rows]


async def default_profile(tenant_id) -> dict | None:
    row = await db.pool().fetchrow(
        'SELECT * FROM quote_profiles WHERE tenant_id=$1 AND active ORDER BY is_default DESC, created_at LIMIT 1',
        tenant_id)
    return dict(row) if row else None


@router.post('', status_code=201)
async def create(body: ProfileBody, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'editor')
    pool = db.pool()
    if body.is_default:
        await pool.execute('UPDATE quote_profiles SET is_default=false WHERE tenant_id=$1', user['tenant_id'])
    row = await pool.fetchrow(
        'INSERT INTO quote_profiles(tenant_id,name,unit,rate_cents,waste_percent,minimum_cents,measurement,'
        'currency,tax_basis_points,is_default,active,notes) '
        'VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *',
        user['tenant_id'], body.name.strip(), body.unit.strip(), body.rate_cents, body.waste_percent,
        body.minimum_cents, body.measurement, body.currency, body.tax_basis_points, body.is_default,
        body.active, body.notes)
    return view(row)


@router.patch('/{profile_id}')
async def update(profile_id: UUID, body: ProfileBody, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'editor')
    pool = db.pool()
    if body.is_default:
        await pool.execute('UPDATE quote_profiles SET is_default=false WHERE tenant_id=$1', user['tenant_id'])
    row = await pool.fetchrow(
        'UPDATE quote_profiles SET name=$3, unit=$4, rate_cents=$5, waste_percent=$6, minimum_cents=$7, '
        'measurement=$8, currency=$9, tax_basis_points=$10, is_default=$11, active=$12, notes=$13, '
        'updated_at=now() WHERE tenant_id=$1 AND id=$2 RETURNING *',
        user['tenant_id'], profile_id, body.name.strip(), body.unit.strip(), body.rate_cents,
        body.waste_percent, body.minimum_cents, body.measurement, body.currency, body.tax_basis_points,
        body.is_default, body.active, body.notes)
    if not row:
        raise HTTPException(404, 'Quoting method not found')
    return view(row)


@router.delete('/{profile_id}', status_code=204)
async def remove(profile_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'editor')
    result = await db.pool().execute(
        'UPDATE quote_profiles SET active=false, is_default=false, updated_at=now() '
        'WHERE tenant_id=$1 AND id=$2', user['tenant_id'], profile_id)
    if result.endswith(' 0'):
        raise HTTPException(404, 'Quoting method not found')
