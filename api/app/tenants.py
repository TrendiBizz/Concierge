import re
import secrets

from . import db

UPDATABLE_FIELDS = {
    "name": str,
    "site_url": str,
    "allowed_origins": list,
    "persona": str,
    "greeting": str,
    "cta_text": str,
    "accent_color": str,
    "voice": str,
    "voice_enabled": bool,
    "voice_daily_limit": int,
    "booking_url": str,
    "lead_webhook_url": str,
    "incentive": str,
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "tenant"


def new_public_key() -> str:
    return "pk_" + secrets.token_urlsafe(18)


async def get_by_key(public_key: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE public_key = $1", public_key)
    return dict(row) if row else None


async def get_by_slug(slug: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug = $1", slug)
    return dict(row) if row else None


async def list_all() -> list[dict]:
    rows = await db.pool().fetch("SELECT * FROM tenants ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def create(name: str, site_url: str | None, slug: str | None = None, **fields) -> dict:
    slug = slugify(slug or name)
    # Make the slug unique rather than failing on a name clash.
    base, n = slug, 1
    while await get_by_slug(slug):
        n += 1
        slug = f"{base}-{n}"

    row = await db.pool().fetchrow(
        """
        INSERT INTO tenants (slug, name, public_key, site_url, allowed_origins, persona,
                             greeting, booking_url, lead_webhook_url, incentive)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING *
        """,
        slug,
        name,
        new_public_key(),
        site_url,
        fields.get("allowed_origins") or [],
        fields.get("persona") or "",
        fields.get("greeting") or "",
        fields.get("booking_url"),
        fields.get("lead_webhook_url"),
        fields.get("incentive") or "",
    )
    return dict(row)


async def update(slug: str, fields: dict) -> dict | None:
    clean = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS and v is not None}
    if not clean:
        return await get_by_slug(slug)
    assignments = ", ".join(f"{col} = ${i}" for i, col in enumerate(clean, start=2))
    row = await db.pool().fetchrow(
        f"UPDATE tenants SET {assignments} WHERE slug = $1 RETURNING *",
        slug,
        *clean.values(),
    )
    return dict(row) if row else None


async def delete(slug: str) -> bool:
    result = await db.pool().execute("DELETE FROM tenants WHERE slug = $1", slug)
    return result.endswith("1")


def public_view(tenant: dict) -> dict:
    """Fields safe to return to the browser."""
    return {
        "name": tenant["name"],
        "greeting": tenant["greeting"]
        or f"Hi! I'm {tenant['name']}'s AI guide. Ask me anything about our business.",
        "cta_text": tenant["cta_text"],
        "accent_color": tenant["accent_color"],
        "voice_enabled": tenant["voice_enabled"],
    }
