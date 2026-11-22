"""Postgres-backed store for Concierge Social accounts, OAuth states, posts, approvals, and results.

All OAuth access and refresh tokens are encrypted at rest with Concierge's N9 crypto_vault
(AES-256-GCM) bound via AAD to `social:{customer_slug}:{network}:{external_id}`.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from .. import crypto_vault, db
from . import guardrails

VALID_STATUSES = {
    "draft",
    "pending_approval",
    "approved",
    "scheduled",
    "publishing",
    "processing",
    "published",
    "failed",
    "rejected",
}


def random_id() -> str:
    return secrets.token_urlsafe(24)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def account_aad(customer_slug: str, network: str, external_id: str) -> str:
    return f"social:{customer_slug}:{network}:{external_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _from_ts(ts: int | float | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _to_unix(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


async def ensure_customer(slug: str, name: str, approval_contact: str = "") -> str:
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "Invalid tenant slug")
    await db.pool().execute(
        """INSERT INTO social_customers(slug, name, rules, approval_contact)
           VALUES($1, $2, '{}'::jsonb, $3)
           ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name""",
        slug,
        (name or slug)[:200],
        (approval_contact or "")[:200],
    )
    return slug


async def get_rules(customer_slug: str) -> dict:
    raw = await db.pool().fetchval("SELECT rules FROM social_customers WHERE slug=$1", customer_slug)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return dict(raw) if isinstance(raw, dict) else {}


async def update_rules(customer_slug: str, rules: dict) -> None:
    res = await db.pool().execute(
        "UPDATE social_customers SET rules=$2::jsonb WHERE slug=$1",
        customer_slug,
        json.dumps(rules or {}),
    )
    if not res.endswith(" 1"):
        raise HTTPException(404, "Social workspace not found")


async def list_accounts(customer_slug: str) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT id, customer_slug, network, external_id, display_name,
                  granted_scopes, expires_at, needs_reauth, authorized_at
           FROM social_accounts
           WHERE customer_slug=$1 AND disconnected_at IS NULL
           ORDER BY created_at ASC""",
        customer_slug,
    )
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "customer_id": r["customer_slug"],
            "network": r["network"],
            "external_id": r["external_id"],
            "display_name": r["display_name"],
            "granted_scopes": r["granted_scopes"],
            "needs_reauth": bool(r["needs_reauth"]),
            "expires_at": _to_unix(r["expires_at"]),
            "authorized_at": _to_unix(r["authorized_at"]),
        })
    return out


async def upsert_verified_account(
    *,
    customer_slug: str,
    network: str,
    external_id: str,
    display_name: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: int | None = None,
    granted_scopes: str = "",
) -> str:
    if not network or not external_id or not access_token:
        raise HTTPException(400, "Invalid social account credentials")
    aad = account_aad(customer_slug, network, external_id)
    tok_enc = crypto_vault.encrypt_text(access_token, aad=aad)
    ref_enc = crypto_vault.encrypt_text(refresh_token, aad=aad) if refresh_token else None
    exp_dt = _from_ts(expires_at)

    existing = await db.pool().fetchval(
        """SELECT id FROM social_accounts
           WHERE customer_slug=$1 AND network=$2 AND external_id=$3""",
        customer_slug,
        network,
        external_id,
    )
    account_id = existing or random_id()
    await db.pool().execute(
        """INSERT INTO social_accounts(
               id, customer_slug, network, external_id, display_name,
               token_enc, refresh_enc, granted_scopes, authorized_at,
               disconnected_at, expires_at, needs_reauth)
           VALUES($1, $2, $3, $4, $5, $6, $7, $8, now(), NULL, $9, false)
           ON CONFLICT (id) DO UPDATE SET
               display_name = EXCLUDED.display_name,
               token_enc = EXCLUDED.token_enc,
               refresh_enc = COALESCE(EXCLUDED.refresh_enc, social_accounts.refresh_enc),
               granted_scopes = EXCLUDED.granted_scopes,
               authorized_at = now(),
               disconnected_at = NULL,
               expires_at = EXCLUDED.expires_at,
               needs_reauth = false""",
        account_id,
        customer_slug,
        network,
        external_id,
        (display_name or external_id)[:200],
        tok_enc,
        ref_enc,
        granted_scopes or "",
        exp_dt,
    )
    await record_event(customer_slug, None, "account.connected", f"{network}:{external_id}")
    return account_id


async def get_account_credentials(
    customer_slug: str, account_id: str, *, allow_expired: bool = False
) -> dict:
    row = await db.pool().fetchrow(
        """SELECT id, network, external_id, display_name, token_enc, refresh_enc,
                  granted_scopes, expires_at, needs_reauth, disconnected_at
           FROM social_accounts
           WHERE id=$1 AND customer_slug=$2""",
        account_id,
        customer_slug,
    )
    if not row or row["disconnected_at"] is not None:
        raise HTTPException(404, "Social account not found")
    if row["needs_reauth"] and not allow_expired:
        raise HTTPException(409, "Social account requires reconnection")
    if not allow_expired and row["expires_at"] and row["expires_at"] <= _now():
        raise HTTPException(409, "Social account token expired; renew or reconnect")

    aad = account_aad(customer_slug, row["network"], row["external_id"])
    try:
        access_token = crypto_vault.decrypt_text(row["token_enc"], aad=aad, allow_plaintext=False)
        refresh_token = (
            crypto_vault.decrypt_text(row["refresh_enc"], aad=aad, allow_plaintext=False)
            if row["refresh_enc"]
            else None
        )
    except ValueError as exc:
        raise HTTPException(500, "Stored social credentials could not be decrypted") from exc

    return {
        "id": row["id"],
        "network": row["network"],
        "external_id": row["external_id"],
        "display_name": row["display_name"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_enc": row["token_enc"],
        "granted_scopes": row["granted_scopes"] or "",
        "expires_at": _to_unix(row["expires_at"]),
        "needs_reauth": bool(row["needs_reauth"]),
    }


async def update_refreshed_token(
    *,
    customer_slug: str,
    account_id: str,
    network: str,
    external_id: str,
    expected_old_token_enc: str,
    new_access_token: str,
    new_refresh_token: str | None,
    new_expires_at: int,
) -> None:
    aad = account_aad(customer_slug, network, external_id)
    new_tok_enc = crypto_vault.encrypt_text(new_access_token, aad=aad)
    new_ref_enc = crypto_vault.encrypt_text(new_refresh_token, aad=aad) if new_refresh_token else None
    res = await db.pool().execute(
        """UPDATE social_accounts
           SET token_enc=$1,
               refresh_enc=COALESCE($2, refresh_enc),
               expires_at=$3,
               needs_reauth=false
           WHERE id=$4 AND customer_slug=$5 AND token_enc=$6 AND disconnected_at IS NULL""",
        new_tok_enc,
        new_ref_enc,
        _from_ts(new_expires_at),
        account_id,
        customer_slug,
        expected_old_token_enc,
    )
    if not res.endswith(" 1"):
        raise HTTPException(409, "Social token changed concurrently or account was disconnected")
    await record_event(customer_slug, None, "account.token_refreshed", f"{network}:{account_id}")


async def mark_needs_reauth(customer_slug: str, account_id: str) -> None:
    await db.pool().execute(
        "UPDATE social_accounts SET needs_reauth=true WHERE id=$1 AND customer_slug=$2",
        account_id,
        customer_slug,
    )


async def disconnect_account(customer_slug: str, account_id: str, expected_network: str | None = None) -> dict:
    row = await db.pool().fetchrow(
        """SELECT id, network, external_id, token_enc, refresh_enc
           FROM social_accounts
           WHERE id=$1 AND customer_slug=$2 AND disconnected_at IS NULL""",
        account_id,
        customer_slug,
    )
    if not row:
        raise HTTPException(404, "Social account not found")
    if expected_network and row["network"] != expected_network:
        if not (expected_network == "linkedin" and row["network"] == "linkedin_organization"):
            raise HTTPException(404, "Social account not found for this network")
    aad = account_aad(customer_slug, row["network"], row["external_id"])
    token = ""
    try:
        token = crypto_vault.decrypt_text(row["token_enc"], aad=aad, allow_plaintext=False)
    except ValueError:
        pass
    await db.pool().execute(
        """UPDATE social_accounts
           SET disconnected_at=now(), needs_reauth=true, token_enc='revoked', refresh_enc=NULL
           WHERE id=$1 AND customer_slug=$2""",
        account_id,
        customer_slug,
    )
    await record_event(customer_slug, None, "account.disconnected", f"{row['network']}:{account_id}")
    return {"id": account_id, "network": row["network"], "external_id": row["external_id"], "access_token": token}


async def account_has_scope(customer_slug: str, account_id: str, scope: str) -> bool:
    granted = await db.pool().fetchval(
        """SELECT granted_scopes FROM social_accounts
           WHERE id=$1 AND customer_slug=$2 AND disconnected_at IS NULL AND NOT needs_reauth""",
        account_id,
        customer_slug,
    )
    if not granted:
        return False
    tokens = granted.replace(",", " ").split()
    return scope in tokens


# ---- OAuth PKCE state (atomic one-use, tenant-bound) ----------------------------------------
async def oauth_begin(customer_slug: str, network: str, state: str, verifier: str, ttl_seconds: int = 600) -> None:
    if ttl_seconds <= 0 or ttl_seconds > 900 or len(state) < 32:
        raise HTTPException(400, "Invalid OAuth state")
    enc = crypto_vault.encrypt_text(verifier, aad=f"social-oauth:{customer_slug}:{network}")
    exp = _now() + timedelta(seconds=ttl_seconds)
    await db.pool().execute("DELETE FROM social_oauth_pending WHERE expires_at <= now()")
    await db.pool().execute(
        """INSERT INTO social_oauth_pending(state_hash, customer_slug, network, verifier_enc, expires_at)
           VALUES($1, $2, $3, $4, $5)""",
        token_hash(state),
        customer_slug,
        network,
        enc,
        exp,
    )


async def oauth_consume(customer_slug: str, network: str, state: str) -> str:
    if not state or len(state) < 32 or len(state) > 256:
        raise HTTPException(400, "OAuth state expired or invalid")
    row = await db.pool().fetchrow(
        """DELETE FROM social_oauth_pending
           WHERE state_hash=$1 AND customer_slug=$2 AND network=$3 AND expires_at > now()
           RETURNING verifier_enc""",
        token_hash(state),
        customer_slug,
        network,
    )
    if not row:
        raise HTTPException(400, "OAuth state expired or invalid")
    try:
        return crypto_vault.decrypt_text(
            row["verifier_enc"], aad=f"social-oauth:{customer_slug}:{network}", allow_plaintext=False
        )
    except ValueError as exc:
        raise HTTPException(400, "OAuth state expired or invalid") from exc


# ---- Posts, Approvals, and Per-Account Results ----------------------------------------------
def _decode_json(val: Any, default: Any):
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except ValueError:
            return default
    return default


def _format_post(row: Any, results: list[dict] | None = None) -> dict:
    return {
        "id": row["id"],
        "customer_id": row["customer_slug"],
        "content": row["content"],
        "link": row["link"],
        "hashtags": row["hashtags"],
        "account_ids": _decode_json(row["account_ids"], []),
        "media": _decode_json(row["media"], []),
        "options": _decode_json(row["options"], {}),
        "status": row["status"],
        "scheduled_at": _to_unix(row["scheduled_at"]),
        "revision": int(row["revision"]),
        "approved_revision": int(row["approved_revision"]) if row["approved_revision"] is not None else None,
        "attempts": int(row["attempts"]),
        "last_error": row["last_error"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "results": results if results is not None else [],
    }


async def list_posts(customer_slug: str, limit: int = 100) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT id, customer_slug, content, link, hashtags, account_ids, media, options,
                  status, scheduled_at, revision, approved_revision, attempts, last_error,
                  created_at, updated_at
           FROM social_posts
           WHERE customer_slug=$1
           ORDER BY created_at DESC
           LIMIT $2""",
        customer_slug,
        limit,
    )
    if not rows:
        return []
    post_ids = [r["id"] for r in rows]
    res_rows = await db.pool().fetch(
        """SELECT r.post_id, r.account_id, r.external_post_id, r.external_url, r.error, r.ok, r.at,
                  a.network, a.display_name
           FROM social_post_results r
           LEFT JOIN social_accounts a ON a.id = r.account_id
           WHERE r.post_id = ANY($1::text[])
           ORDER BY r.at DESC""",
        post_ids,
    )
    by_post: dict[str, list[dict]] = {}
    for rr in res_rows:
        by_post.setdefault(rr["post_id"], []).append({
            "account_id": rr["account_id"],
            "network": rr["network"] or "",
            "account_name": rr["display_name"] or "",
            "external_post_id": rr["external_post_id"],
            "external_url": rr["external_url"],
            "error": rr["error"],
            "ok": bool(rr["ok"]),
            "at": rr["at"].isoformat() if rr["at"] else None,
        })
    return [_format_post(r, by_post.get(r["id"], [])) for r in rows]


async def create_draft(
    customer_slug: str,
    *,
    content: str,
    account_ids: list[str],
    link: str = "",
    hashtags: str = "",
    media: list[str] | None = None,
    options: dict | None = None,
) -> dict:
    if not (content or "").strip() or len(content) > 10000 or not (1 <= len(account_ids) <= 10):
        raise HTTPException(400, "A valid post and one or more accounts are required")
    media = media or []
    options = options or {}
    # Verify all accounts belong to this tenant
    accts = await db.pool().fetch(
        """SELECT id, network FROM social_accounts
           WHERE customer_slug=$1 AND id = ANY($2::text[]) AND disconnected_at IS NULL""",
        customer_slug,
        account_ids,
    )
    if len(accts) != len(set(account_ids)):
        raise HTTPException(400, "One or more selected social accounts are not connected to this business")

    post_id = random_id()
    row = await db.pool().fetchrow(
        """INSERT INTO social_posts(
               id, customer_slug, content, link, hashtags, account_ids, media, options, status, revision)
           VALUES($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, 'draft', 1)
           RETURNING *""",
        post_id,
        customer_slug,
        content.strip(),
        (link or "").strip(),
        (hashtags or "").strip(),
        json.dumps(account_ids),
        json.dumps(media),
        json.dumps(options),
    )
    await record_event(customer_slug, post_id, "post.created", f"accounts={len(account_ids)}")
    return _format_post(row)


async def submit_draft(customer_slug: str, post_id: str) -> dict:
    row = await db.pool().fetchrow(
        "SELECT * FROM social_posts WHERE id=$1 AND customer_slug=$2", post_id, customer_slug
    )
    if not row:
        raise HTTPException(404, "Social post not found")
    if row["status"] not in ("draft", "rejected", "failed"):
        raise HTTPException(409, f"Cannot submit a post in status '{row['status']}'")

    account_ids = _decode_json(row["account_ids"], [])
    acct_rows = await db.pool().fetch(
        """SELECT id, network FROM social_accounts
           WHERE customer_slug=$1 AND id = ANY($2::text[]) AND disconnected_at IS NULL AND NOT needs_reauth""",
        customer_slug,
        account_ids,
    )
    if len(acct_rows) != len(set(account_ids)):
        raise HTTPException(409, "One or more accounts require reconnection before submitting")

    rules = await get_rules(customer_slug)
    media = _decode_json(row["media"], [])
    chk = guardrails.check_post(
        content=row["content"],
        link=row["link"],
        hashtags=row["hashtags"],
        networks=[a["network"] for a in acct_rows],
        media_count=len(media),
        rules=rules,
    )
    if not chk["ok"]:
        msg = "; ".join(e["message"] for e in chk["errors"][:3])
        raise HTTPException(400, msg or "Post failed guardrails")

    updated = await db.pool().fetchrow(
        """UPDATE social_posts
           SET status='pending_approval', last_error=NULL, updated_at=now()
           WHERE id=$1 AND customer_slug=$2
           RETURNING *""",
        post_id,
        customer_slug,
    )
    await record_event(customer_slug, post_id, "post.submitted", f"revision={updated['revision']}")
    return _format_post(updated)


async def request_approval(customer_slug: str, post_id: str, scheduled_at: int) -> dict:
    row = await db.pool().fetchrow(
        "SELECT * FROM social_posts WHERE id=$1 AND customer_slug=$2", post_id, customer_slug
    )
    if not row:
        raise HTTPException(404, "Social post not found")
    if row["status"] != "pending_approval":
        raise HTTPException(409, "Post must be submitted for approval first")

    tok = random_id()
    sched_dt = _from_ts(scheduled_at) if scheduled_at else _now()
    exp_dt = _now() + timedelta(hours=24)
    await db.pool().execute(
        """INSERT INTO social_approvals(token_hash, customer_slug, post_id, revision, scheduled_at, expires_at, used)
           VALUES($1, $2, $3, $4, $5, $6, false)""",
        token_hash(tok),
        customer_slug,
        post_id,
        int(row["revision"]),
        sched_dt,
        exp_dt,
    )
    return {"token": tok, "post_id": post_id, "scheduled_at": _to_unix(sched_dt), "expires_at": _to_unix(exp_dt)}


async def decide_approval(customer_slug: str, token: str, approve: bool) -> dict:
    th = token_hash(token)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            app_row = await conn.fetchrow(
                """UPDATE social_approvals
                   SET used=true
                   WHERE token_hash=$1 AND customer_slug=$2 AND NOT used AND expires_at > now()
                   RETURNING post_id, revision, scheduled_at""",
                th,
                customer_slug,
            )
            if not app_row:
                raise HTTPException(404, "Approval token is invalid, expired, or already used")
            post_row = await conn.fetchrow(
                "SELECT * FROM social_posts WHERE id=$1 AND customer_slug=$2 FOR UPDATE",
                app_row["post_id"],
                customer_slug,
            )
            if not post_row or int(post_row["revision"]) != int(app_row["revision"]):
                raise HTTPException(409, "Post was modified after approval was requested")
            if approve:
                updated = await conn.fetchrow(
                    """UPDATE social_posts
                       SET status='scheduled',
                           approved_revision=$1,
                           scheduled_at=$2,
                           last_error=NULL,
                           updated_at=now()
                       WHERE id=$3
                       RETURNING *""",
                    int(app_row["revision"]),
                    app_row["scheduled_at"] or _now(),
                    app_row["post_id"],
                )
            else:
                updated = await conn.fetchrow(
                    """UPDATE social_posts
                       SET status='draft',
                           approved_revision=NULL,
                           scheduled_at=NULL,
                           updated_at=now()
                       WHERE id=$1
                       RETURNING *""",
                    app_row["post_id"],
                )
    await record_event(
        customer_slug,
        updated["id"],
        "post.approved" if approve else "post.rejected",
        f"revision={updated['revision']}",
    )
    return _format_post(updated)


async def quarantine_interrupted() -> int:
    rows = await db.pool().fetch(
        """UPDATE social_posts
           SET status='failed',
               last_error='Interrupted during server restart; review before retrying',
               updated_at=now()
           WHERE status='publishing'
           RETURNING id"""
    )
    return len(rows)


async def claim_due_posts(now: datetime | None = None, limit: int = 10) -> list[dict]:
    now = now or _now()
    rows = await db.pool().fetch(
        """UPDATE social_posts
           SET status='publishing', attempts=attempts + 1, updated_at=now()
           WHERE id IN (
               SELECT id FROM social_posts
               WHERE status='scheduled'
                 AND approved_revision = revision
                 AND scheduled_at IS NOT NULL
                 AND scheduled_at <= $1
               ORDER BY scheduled_at ASC
               LIMIT $2
               FOR UPDATE SKIP LOCKED
           )
           RETURNING *""",
        now,
        limit,
    )
    return [_format_post(r) for r in rows]


async def pending_processing_receipts() -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT p.id AS post_id, p.customer_slug, r.account_id, r.external_post_id
           FROM social_posts p
           JOIN social_post_results r ON r.post_id = p.id
           WHERE p.status='processing' AND r.ok = true AND r.external_post_id LIKE 'pending:%'"""
    )
    return [dict(r) for r in rows]


async def result_exists(post_id: str, account_id: str) -> bool:
    val = await db.pool().fetchval(
        "SELECT 1 FROM social_post_results WHERE post_id=$1 AND account_id=$2 AND ok=true",
        post_id,
        account_id,
    )
    return bool(val)


async def record_post_result(
    post_id: str,
    account_id: str,
    *,
    ok: bool,
    external_post_id: str | None = None,
    external_url: str | None = None,
    error: str | None = None,
) -> None:
    await db.pool().execute(
        """INSERT INTO social_post_results(post_id, account_id, external_post_id, external_url, error, ok, at)
           VALUES($1, $2, $3, $4, $5, $6, now())
           ON CONFLICT (post_id, account_id, ok) DO UPDATE SET
               external_post_id = EXCLUDED.external_post_id,
               external_url = EXCLUDED.external_url,
               error = EXCLUDED.error,
               at = now()""",
        post_id,
        account_id,
        external_post_id,
        external_url,
        error,
        ok,
    )


async def finish_post(
    customer_slug: str,
    post_id: str,
    status: str,
    *,
    last_error: str | None = None,
    reschedule_at: datetime | None = None,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid post status: {status}")
    await db.pool().execute(
        """UPDATE social_posts
           SET status=$1,
               last_error=$2,
               scheduled_at=COALESCE($3, scheduled_at),
               updated_at=now()
           WHERE id=$4 AND customer_slug=$5""",
        status,
        last_error,
        reschedule_at,
        post_id,
        customer_slug,
    )
    await record_event(customer_slug, post_id, f"post.{status}", (last_error or "ok")[:400])


async def record_event(customer_slug: str, post_id: str | None, kind: str, detail: str) -> None:
    await db.pool().execute(
        "INSERT INTO social_events(customer_slug, post_id, kind, detail) VALUES($1, $2, $3, $4)",
        customer_slug,
        post_id,
        kind[:80],
        detail[:500],
    )
