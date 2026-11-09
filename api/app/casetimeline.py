"""Unified customer case timeline — one person, every channel, one durable history.

The problem this solves: a customer who emails on Monday, texts on Tuesday and calls on Wednesday
used to leave three unconnected records, because each channel keyed its own conversation
(a call SID, an email-address hash, an SMS session). The owner could not see that the same person
had already been answered somewhere else, and nothing could detect a message going unanswered
across channels.

A *case* is a customer identity, not a conversation:

    case_key = "phone:+6421555123"   when a usable phone number exists
             = "email:hana@example.com"   otherwise
             = None                    when neither identity is usable

Phone wins because it survives an email address change. A key is only produced from an identity we
can be confident about, so two different customers are never merged into one case: an unusable
phone or empty email yields None rather than a shared bucket.

Two safety rules are enforced here, both because the alternative loses money or trust:
  - Every write is idempotent on (tenant_id, channel, source_key). Provider webhooks retry.
  - Human takeover is recorded per case, so a personal reply stops the automation for that customer.

Nothing in this module sends anything. It records and links; delivery stays in outbox.py.
"""

import hashlib
from datetime import datetime, timezone

from . import db
from .config import get_settings
from .contact import is_email, normalize_phone

CHANNELS = ("chat", "voice", "email", "sms", "phone", "social")
DIRECTIONS = ("inbound", "outbound")


def tenant_country_code(tenant: dict | None) -> str:
    """The dialling country to use for a tenant's local numbers.

    Prefers the tenant's own country code and only then the global setting. Without this a business
    outside +1 had its 10-digit local numbers prefixed with '1', which produced a wrong number and --
    worse for this module -- split one customer across two case identities.
    """
    if tenant:
        own = str(tenant.get("default_country_code") or "").strip()
        if own.isdigit() and 1 <= len(own) <= 3:
            return own
    return get_settings().default_country_code


def case_key(phone: str = "", email: str = "", default_cc: str = "1") -> str | None:
    """The stable identity for a customer, or None when neither identifier is usable.

    Returning None for unusable input is deliberate. Falling back to, say, the raw string would
    merge unrelated strangers who both sent a malformed number into one shared case history.
    """
    normalised = normalize_phone(phone or "", default_cc)
    if normalised:
        return f"phone:{normalised}"
    candidate = (email or "").strip().lower()
    if candidate and is_email(candidate):
        return f"email:{candidate}"
    return None


def case_key_for_tenant(tenant: dict | None, phone: str = "", email: str = "") -> str | None:
    """case_key() using the tenant's own dialling country."""
    return case_key(phone, email, tenant_country_code(tenant))


def source_key_for(channel: str, identifier: str, body: str = "") -> str:
    """A stable key for one inbound event, so a retried webhook does not duplicate the history.

    Provider ids are hashed rather than stored, so a provider's own id scheme never leaks into a
    lookup path or a unique index. The body is included only when the caller has no unique id,
    which keeps two genuinely different messages apart while collapsing a true replay.
    """
    material = f"{channel}\x00{identifier}\x00{body}" if not identifier else f"{channel}\x00{identifier}"
    return hashlib.sha256(material.encode()).hexdigest()


async def ensure_case(tenant_id, *, phone: str = "", email: str = "", name: str = "",
                      default_cc: str = "1") -> dict | None:
    """Find or create the case for this identity. None when the identity is unusable.

    Upsert rather than select-then-insert: two channels can arrive concurrently for the same new
    customer, and a race must not create two cases for one person.
    """
    key = case_key(phone, email, default_cc)
    if key is None:
        return None
    phone_norm = (normalize_phone(phone, default_cc) or "")[:40]
    email_norm = (email or "").strip().lower()[:200]
    row = await db.pool().fetchrow(
        """
        INSERT INTO customer_cases (tenant_id, case_key, display_name, primary_phone, primary_email)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (tenant_id, case_key) DO UPDATE SET
            display_name  = COALESCE(NULLIF(EXCLUDED.display_name, ''),  customer_cases.display_name),
            primary_phone = COALESCE(NULLIF(EXCLUDED.primary_phone, ''), customer_cases.primary_phone),
            primary_email = COALESCE(NULLIF(EXCLUDED.primary_email, ''), customer_cases.primary_email),
            updated_at    = now()
        RETURNING *
        """,
        tenant_id, key, (name or "")[:200], phone_norm, email_norm,
    )
    return dict(row) if row else None


async def reconcile(tenant_id, *, phone: str = "", email: str = "", name: str = "",
                    default_cc: str = "1") -> dict | None:
    """Resolve the customer's case, MERGING any cases that turn out to be the same person.

    Without this, one customer becomes several: writing first leaves an `email:...` case, then a
    phone-only call creates a separate `phone:...` case, and the owner sees one person as strangers.
    This is the core 'unify the customer' requirement.

    Identification uses BOTH the case key and the stored primary_phone/primary_email, because a
    phone-only message must still find a case that was created from an email (and vice versa). Using
    the key alone was not enough: a phone-only call could not see the email-keyed case at all.

    Where several cases match, the strongest identity survives -- a phone-keyed case over an
    email-keyed one, since a phone number outlives an email address. Everything else is repointed
    onto the survivor and the duplicate rows are removed.
    """
    phone_key = case_key(phone, "", default_cc)
    email_key = case_key("", email, default_cc)
    phone_norm = normalize_phone(phone, default_cc) or ""
    email_norm = (email or "").strip().lower()

    if phone_key is None and email_key is None:
        return None  # no usable identity: never invent a shared case for an unknown person

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            # Serialise concurrent reconciliation for this identity pair.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                               f"case:{tenant_id}:{phone_key or '-'}:{email_key or '-'}")

            # Every existing case this customer matches, by key OR by stored identifier.
            matches = await conn.fetch(
                """
                SELECT * FROM customer_cases
                WHERE tenant_id = $1
                  AND ( case_key = ANY($2::text[])
                        OR ($3 <> '' AND primary_phone = $3)
                        OR ($4 <> '' AND primary_email = $4) )
                ORDER BY (case_key = $5) DESC, created_at
                """,
                tenant_id,
                [k for k in (phone_key, email_key) if k],
                phone_norm, email_norm,
                phone_key or "",
            )

            if not matches:
                # First sighting: create the new case.
                return await ensure_case(
                    tenant_id, phone=phone, email=email, name=name, default_cc=default_cc)

            survivor = matches[0]
            for duplicate in matches[1:]:
                await _merge_into(conn, survivor, duplicate)

            # Adopt the newly supplied identifier so the survivor is findable by both next time.
            await conn.execute(
                """
                UPDATE customer_cases SET
                    primary_phone = COALESCE(NULLIF(primary_phone,''), $2),
                    primary_email = COALESCE(NULLIF(primary_email,''), $3),
                    display_name  = COALESCE(NULLIF(display_name,''), $4),
                    updated_at    = now()
                WHERE id = $1
                """,
                survivor["id"], phone_norm[:40], email_norm[:200], (name or "")[:200])

            # A phone number that arrived later should take over the key, so future phone-only
            # traffic resolves directly instead of re-running a merge every time.
            if phone_key and survivor["case_key"] != phone_key:
                taken = await conn.fetchval(
                    "SELECT 1 FROM customer_cases WHERE tenant_id=$1 AND case_key=$2 AND id<>$3",
                    tenant_id, phone_key, survivor["id"])
                if not taken:
                    survivor = await conn.fetchrow(
                        "UPDATE customer_cases SET case_key=$2, updated_at=now() WHERE id=$1 RETURNING *",
                        survivor["id"], phone_key)

            return dict(survivor)


async def _merge_into(conn, survivor, duplicate) -> None:
    """Fold one duplicate case into the survivor, then delete it.

    Order matters: every dependent row is repointed BEFORE the delete, and takeover state is OR-ed
    onto the survivor rather than overwritten -- a duplicate the owner had personally taken over
    must not silently restart automation on the merged case.
    """
    await conn.execute(
        """
        UPDATE customer_cases SET
            primary_phone     = COALESCE(NULLIF(primary_phone, ''), $2),
            primary_email     = COALESCE(NULLIF(primary_email, ''), $3),
            display_name      = COALESCE(NULLIF(display_name, ''), $4),
            automation_paused = automation_paused OR $5,
            takeover_at       = COALESCE(takeover_at, $6),
            updated_at        = now()
        WHERE id = $1
        """,
        survivor["id"], duplicate["primary_phone"], duplicate["primary_email"],
        duplicate["display_name"], duplicate["automation_paused"], duplicate["takeover_at"])
    await conn.execute("UPDATE case_events SET case_id=$1 WHERE case_id=$2", survivor["id"], duplicate["id"])
    await conn.execute("UPDATE leads SET case_id=$1 WHERE case_id=$2", survivor["id"], duplicate["id"])
    await conn.execute("UPDATE conversations SET case_id=$1 WHERE case_id=$2", survivor["id"], duplicate["id"])
    await conn.execute("UPDATE tasks SET case_id=$1 WHERE case_id=$2", survivor["id"], duplicate["id"])
    await conn.execute("DELETE FROM customer_cases WHERE id=$1", duplicate["id"])


async def record(
    tenant_id, *, case_key: str, channel: str, direction: str,
    source_key: str, body: str = "", occurred_at: datetime | None = None,
) -> dict | None:
    """Append one event to a case's history. Idempotent on (tenant, channel, source_key)."""
    if channel not in CHANNELS:
        raise ValueError(f"Unsupported channel: {channel}")
    if direction not in DIRECTIONS:
        raise ValueError(f"Unsupported direction: {direction}")
    row = await db.pool().fetchrow(
        """
        WITH target AS (SELECT id FROM customer_cases WHERE tenant_id = $1 AND case_key = $2)
        INSERT INTO case_events (case_id, tenant_id, channel, direction, source_key, body, occurred_at)
        SELECT target.id, $1, $3, $4, $5, $6, COALESCE($7, now()) FROM target
        ON CONFLICT (tenant_id, channel, source_key) DO NOTHING
        RETURNING *
        """,
        tenant_id, case_key, channel, direction, source_key[:200], (body or "")[:30000],
        occurred_at or datetime.now(timezone.utc),
    )
    if row:
        await db.pool().execute(
            "UPDATE customer_cases SET updated_at = now() WHERE tenant_id = $1 AND case_key = $2",
            tenant_id, case_key)
    return dict(row) if row else None


async def record_message(
    tenant_id, *, phone: str = "", email: str = "", name: str = "",
    channel: str, direction: str, source_key: str, body: str = "",
) -> dict | None:
    """Convenience path used by channel ingress: resolve the case, then record the message."""
    case = await ensure_case(tenant_id, phone=phone, email=email, name=name)
    if case is None:
        return None
    return await record(
        tenant_id, case_key=case["case_key"], channel=channel,
        direction=direction, source_key=source_key, body=body,
    )


async def mark_answered(tenant_id, *, channel: str, source_key: str) -> int:
    """Stamp an inbound message as answered. Called when the owner or the assistant replies."""
    result = await db.pool().execute(
        """
        UPDATE case_events SET answered_at = now()
        WHERE tenant_id = $1 AND channel = $2 AND source_key = $3
          AND direction = 'inbound' AND answered_at IS NULL
        """,
        tenant_id, channel, source_key[:200],
    )
    return int(result.split()[-1] or 0)


async def set_takeover(tenant_id, *, case_key: str, paused: bool, by: str = "owner") -> bool:
    """Pause or resume automation for one customer after a personal reply.

    This is the 'the owner already handled it' switch. Without it the assistant keeps replying to
    someone the business owner is already talking to, which is the fastest way to lose trust.
    """
    result = await db.pool().execute(
        """
        UPDATE customer_cases
        SET automation_paused = $3,
            takeover_at = CASE WHEN $3 THEN now() ELSE NULL END,
            takeover_by = CASE WHEN $3 THEN $4 ELSE '' END,
            updated_at  = now()
        WHERE tenant_id = $1 AND case_key = $2
        """,
        tenant_id, case_key, bool(paused), (by or "")[:100],
    )
    return result.endswith("1")


async def is_paused(tenant_id, case_key: str) -> bool:
    """True when the owner has taken over this customer and automation must stay quiet."""
    if not case_key:
        return False
    return bool(await db.pool().fetchval(
        "SELECT automation_paused FROM customer_cases WHERE tenant_id = $1 AND case_key = $2",
        tenant_id, case_key))


async def timeline(tenant_id, case_key: str, limit: int = 200) -> list[dict]:
    """The customer's full history across every channel, newest first."""
    rows = await db.pool().fetch(
        """
        SELECT e.id, e.channel, e.direction, e.body, e.occurred_at, e.answered_at
        FROM case_events e
        JOIN customer_cases c ON c.id = e.case_id
        WHERE c.tenant_id = $1 AND c.case_key = $2
        ORDER BY e.occurred_at DESC, e.id DESC
        LIMIT $3
        """,
        tenant_id, case_key, int(min(max(limit, 1), 500)),
    )
    return [dict(r) for r in rows]
