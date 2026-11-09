import json
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
    "phone_enabled": bool,
    "phone_daily_limit": int,
    "booking_url": str,
    "lead_webhook_url": str,
    "incentive": str,
    "timezone": str,
    "business_hours": dict,
    "slot_minutes": int,
    "min_notice_hours": int,
    "max_days_ahead": int,
    "native_booking": bool,
    "notify_email": str,
    "notify_phone": str,
    "email_auto_reply": bool,
    "sms_enabled": bool,
    "sms_from": str,
    "lead_sms_template": str,
    "review_url": str,
    "lead_value_cents": int,
    "sla_minutes": int,
    "sla_min_score": int,
    "campaigns_enabled": bool,
    "scoring": dict,
    "weekly_digest": bool,
}
JSONB_FIELDS = {"business_hours", "scoring"}

# Copied by "clone" (a snapshot of settings, never knowledge, contacts or keys).
CLONE_FIELDS = [
    "persona", "greeting", "cta_text", "accent_color", "voice", "voice_enabled",
    "voice_daily_limit", "incentive", "timezone", "business_hours", "slot_minutes",
    "min_notice_hours", "max_days_ahead", "native_booking", "sms_enabled",
    "lead_sms_template", "lead_value_cents",
]


def _load(row) -> dict:
    data = dict(row)
    for key in ("business_hours", "demo_questions"):
        if isinstance(data.get(key), str):
            data[key] = json.loads(data[key])
    return data


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80].rstrip("-") or "tenant"


def new_public_key() -> str:
    return "pk_" + secrets.token_urlsafe(18)


def new_report_token() -> str:
    return secrets.token_urlsafe(24)


async def get_by_key(public_key: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE public_key = $1", public_key)
    return _load(row) if row else None


async def get_by_slug(slug: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug = $1", slug)
    return _load(row) if row else None


async def get_by_id(tenant_id) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    return _load(row) if row else None


async def get_by_report_token(token: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE report_token = $1", token)
    return _load(row) if row else None


async def get_by_calendar_token(token: str) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE calendar_token = $1", token)
    return _load(row) if row else None


async def ensure_calendar_tokens() -> None:
    """Backfill calendar-feed tokens for clients created before the feature existed."""
    for row in await db.pool().fetch("SELECT id FROM tenants WHERE calendar_token IS NULL"):
        await db.pool().execute("UPDATE tenants SET calendar_token = $2 WHERE id = $1", row["id"], new_report_token())


async def ensure_calendar_token(tenant: dict) -> dict:
    """A client's calendar token, created on the spot if it does not have one yet (e.g. inserted by hand)."""
    if tenant.get("calendar_token"):
        return tenant
    row = await db.pool().fetchrow(
        "UPDATE tenants SET calendar_token = COALESCE(calendar_token, $2) WHERE id = $1 RETURNING *",
        tenant["id"], new_report_token())
    return _load(row)


async def list_all() -> list[dict]:
    rows = await db.pool().fetch("SELECT * FROM tenants ORDER BY created_at DESC")
    return [_load(r) for r in rows]


async def ensure_report_tokens() -> None:
    """Backfill report tokens for tenants created before the column existed."""
    rows = await db.pool().fetch("SELECT id FROM tenants WHERE report_token IS NULL")
    for row in rows:
        await db.pool().execute(
            "UPDATE tenants SET report_token = $2 WHERE id = $1", row["id"], new_report_token()
        )


async def create(name: str, site_url: str | None, slug: str | None = None, **fields) -> dict:
    slug = slugify(slug or name)
    # Let the unique constraint arbitrate simultaneous customer creation.
    base, n = slug, 1
    while True:
        row = await db.pool().fetchrow(
            """
            INSERT INTO tenants (slug, name, public_key, report_token, site_url, allowed_origins,
                                 persona, greeting, booking_url, lead_webhook_url, incentive)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (slug) DO NOTHING
            RETURNING *
            """,
            slug,
            name,
            new_public_key(),
            new_report_token(),
            site_url,
            fields.get("allowed_origins") or [],
            fields.get("persona") or "",
            fields.get("greeting") or "",
            fields.get("booking_url"),
            fields.get("lead_webhook_url"),
            fields.get("incentive") or "",
        )
        if row:
            break
        n += 1
        slug = f"{base}-{n}"
    row = await db.pool().fetchrow(
        "UPDATE tenants SET calendar_token = $2 WHERE id = $1 RETURNING *", row["id"], new_report_token())
    return _load(row)


async def update(slug: str, fields: dict) -> dict | None:
    clean = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS and v is not None}
    if not clean:
        return await get_by_slug(slug)
    parts, values = [], []
    for i, (col, value) in enumerate(clean.items(), start=2):
        if col in JSONB_FIELDS:
            parts.append(f"{col} = ${i}::jsonb")
            values.append(json.dumps(value))
        else:
            parts.append(f"{col} = ${i}")
            values.append(value)
    row = await db.pool().fetchrow(
        f"UPDATE tenants SET {', '.join(parts)} WHERE slug = $1 RETURNING *", slug, *values
    )
    return _load(row) if row else None


async def clone(source: dict, name: str, site_url: str | None, slug: str | None = None) -> dict:
    """Snapshot: new tenant with the source's settings but fresh keys and an empty knowledge base."""
    new = await create(name, site_url, slug=slug)
    copied = {field: source[field] for field in CLONE_FIELDS if source.get(field) is not None}
    return await update(new["slug"], copied) or new


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
