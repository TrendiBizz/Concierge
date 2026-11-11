"""Company product catalogue and inventory. Sale price only for staff and AI;
cost price is owner-only and never leaves the database for anyone else."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import db, owner_auth

router = APIRouter(prefix="/owner/products", tags=["products"])


class ProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit: str = Field(default="each", min_length=1, max_length=20)
    sale_price_cents: int = Field(ge=0, le=100_000_000, strict=True)
    cost_price_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    stock_quantity: int = Field(default=0, ge=-1_000_000, le=1_000_000, strict=True)
    active: bool = True


class StockAdjust(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delta: int = Field(ge=-1_000_000, le=1_000_000, strict=True)
    reason: str = Field(default="", max_length=200)


def view(row, role: str) -> dict:
    result = dict(row)
    if role != "owner":
        result.pop("cost_price_cents", None)
    return result


@router.get("")
async def listing(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    rows = await db.pool().fetch(
        "SELECT * FROM products WHERE tenant_id=$1 ORDER BY active DESC, name",
        user["tenant_id"])
    return [view(row, user["role"]) for row in rows]


@router.post("", status_code=201)
async def create(body: ProductIn, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        """INSERT INTO products(tenant_id,sku,name,description,unit,sale_price_cents,
                                 cost_price_cents,stock_quantity,active)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
        user["tenant_id"], body.sku.strip(), body.name.strip(), body.description.strip(),
        body.unit.strip(), body.sale_price_cents, body.cost_price_cents,
        body.stock_quantity, body.active)
    return view(row, user["role"])


@router.put("/{product_id}")
async def update(product_id: UUID, body: ProductIn, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        """UPDATE products SET sku=$3,name=$4,description=$5,unit=$6,sale_price_cents=$7,
                                 cost_price_cents=$8,stock_quantity=$9,active=$10,updated_at=now()
           WHERE tenant_id=$1 AND id=$2 RETURNING *""",
        user["tenant_id"], product_id, body.sku.strip(), body.name.strip(),
        body.description.strip(), body.unit.strip(), body.sale_price_cents,
        body.cost_price_cents, body.stock_quantity, body.active)
    if not row:
        raise HTTPException(404, "Product not found")
    return view(row, user["role"])


@router.post("/{product_id}/stock")
async def adjust_stock(product_id: UUID, body: StockAdjust, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id FROM products WHERE tenant_id=$1 AND id=$2 FOR UPDATE",
                user["tenant_id"], product_id)
            if not row:
                raise HTTPException(404, "Product not found")
            await conn.execute(
                "INSERT INTO product_stock_movements(tenant_id,product_id,delta,reason,actor) "
                "VALUES($1,$2,$3,$4,$5)",
                user["tenant_id"], product_id, body.delta, body.reason.strip(),
                user.get("email", ""))
            updated = await conn.fetchrow(
                "UPDATE products SET stock_quantity=stock_quantity+$3,updated_at=now() "
                "WHERE tenant_id=$1 AND id=$2 RETURNING *",
                user["tenant_id"], product_id, body.delta)
    return view(updated, user["role"])


@router.delete("/{product_id}")
async def deactivate(product_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "UPDATE products SET active=false,updated_at=now() WHERE tenant_id=$1 AND id=$2 RETURNING *",
        user["tenant_id"], product_id)
    if not row:
        raise HTTPException(404, "Product not found")
    return view(row, user["role"])
