#!/usr/bin/env python3
"""Idempotently migrate legacy social SQLite DB + Rust vault tokens into Concierge Postgres.

- Reads the legacy SQLite DB in read-only mode (never modifies or deletes it).
- Decrypts each account's access/refresh token using the legacy SOCIAL_VAULT_KEY
  (AES-256-GCM, 12-byte nonce + ciphertext, AAD = "{customer_id}|{network}|{external_id}").
- Re-encrypts every token using Concierge's N9 `app.crypto_vault.encrypt_text`
  with AAD = "social:{customer_slug}:{network}:{external_id}".
- Never prints tokens, keys, or secrets.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root or /srv inside container
for candidate in (Path(__file__).resolve().parents[2] / "api", Path("/srv")):
    if (candidate / "app").is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app import crypto_vault, db  # noqa: E402
from app.social.store import account_aad  # noqa: E402


def open_legacy_vault(key_b64: str, sealed_b64: str, label: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(key_b64.strip())
    if len(key) != 32:
        raise ValueError("Legacy vault key must be 32 bytes")
    raw = base64.b64decode(sealed_b64.strip())
    if len(raw) < 13:
        raise ValueError("Legacy sealed token too short")
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ct, label.encode("utf-8")).decode("utf-8")


def _ts(val) -> datetime | None:
    if val is None:
        return None
    return datetime.fromtimestamp(int(val), tz=timezone.utc)


async def migrate_sqlite_to_postgres(sqlite_path: str, vault_key_b64: str, *, dry_run: bool = False) -> dict:
    uri = f"file:{sqlite_path}?mode=ro"
    sconn = sqlite3.connect(uri, uri=True)
    sconn.row_factory = sqlite3.Row
    counts = {
        "customers": 0,
        "accounts": 0,
        "accounts_reencrypted": 0,
        "posts": 0,
        "approvals": 0,
        "post_results": 0,
        "events": 0,
        "dry_run": dry_run,
    }

    try:
        customers = sconn.execute(
            "SELECT id, name, rules, approval_contact, created_at FROM customers"
        ).fetchall()
        accounts = sconn.execute(
            """SELECT a.id, a.customer_id, a.network, a.external_id, a.display_name,
                      a.token_enc, a.refresh_enc, a.needs_reauth,
                      c.granted_scopes, c.authorized_at, c.disconnected_at,
                      e.expires_at
               FROM accounts a
               LEFT JOIN account_consents c ON c.account_id = a.id
               LEFT JOIN account_expiries e ON e.account_id = a.id"""
        ).fetchall()
        posts = sconn.execute(
            "SELECT id, customer_id, body, status, scheduled_at, revision, approved_revision FROM posts"
        ).fetchall()
        approvals = sconn.execute(
            "SELECT token_hash, customer_id, post_id, revision, scheduled_at, expires_at, used FROM approvals"
        ).fetchall()
        results = sconn.execute(
            "SELECT post_id, account_id, external_post_id, error, at, ok FROM post_results"
        ).fetchall()
        events = sconn.execute(
            "SELECT at, customer_id, post_id, kind, detail FROM events"
        ).fetchall()

        if dry_run:
            for a in accounts:
                if a["disconnected_at"] is None and a["token_enc"] and a["token_enc"] != "revoked":
                    label = f"{a['customer_id']}|{a['network']}|{a['external_id']}"
                    open_legacy_vault(vault_key_b64, a["token_enc"], label)
                    counts["accounts_reencrypted"] += 1
            counts["customers"] = len(customers)
            counts["accounts"] = len(accounts)
            counts["posts"] = len(posts)
            counts["approvals"] = len(approvals)
            counts["post_results"] = len(results)
            counts["events"] = len(events)
            return counts

        pool = db.pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for c in customers:
                    rules_json = c["rules"] if isinstance(c["rules"], str) else json.dumps(c["rules"] or {})
                    await conn.execute(
                        """INSERT INTO social_customers(slug, name, rules, approval_contact, created_at)
                           VALUES($1, $2, $3::jsonb, $4, COALESCE($5, now()))
                           ON CONFLICT (slug) DO NOTHING""",
                        c["id"], c["name"], rules_json, c["approval_contact"] or "", _ts(c["created_at"]),
                    )
                    counts["customers"] += 1

                for a in accounts:
                    aad = account_aad(a["customer_id"], a["network"], a["external_id"])
                    label = f"{a['customer_id']}|{a['network']}|{a['external_id']}"
                    if a["disconnected_at"] is not None or not a["token_enc"] or a["token_enc"] == "revoked":
                        new_tok = "revoked"
                        new_ref = None
                        needs_reauth = True
                    else:
                        plain_tok = open_legacy_vault(vault_key_b64, a["token_enc"], label)
                        new_tok = crypto_vault.encrypt_text(plain_tok, aad=aad)
                        new_ref = None
                        if a["refresh_enc"]:
                            plain_ref = open_legacy_vault(vault_key_b64, a["refresh_enc"], label)
                            new_ref = crypto_vault.encrypt_text(plain_ref, aad=aad)
                        needs_reauth = bool(a["needs_reauth"])
                        counts["accounts_reencrypted"] += 1

                    await conn.execute(
                        """INSERT INTO social_accounts(
                               id, customer_slug, network, external_id, display_name,
                               token_enc, refresh_enc, granted_scopes, authorized_at,
                               disconnected_at, expires_at, needs_reauth)
                           VALUES($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, now()), $10, $11, $12)
                           ON CONFLICT (id) DO UPDATE SET
                               display_name = EXCLUDED.display_name,
                               token_enc = EXCLUDED.token_enc,
                               refresh_enc = EXCLUDED.refresh_enc,
                               granted_scopes = EXCLUDED.granted_scopes,
                               disconnected_at = EXCLUDED.disconnected_at,
                               expires_at = EXCLUDED.expires_at,
                               needs_reauth = EXCLUDED.needs_reauth""",
                        a["id"], a["customer_id"], a["network"], a["external_id"], a["display_name"] or "",
                        new_tok, new_ref, a["granted_scopes"] or "",
                        _ts(a["authorized_at"]), _ts(a["disconnected_at"]), _ts(a["expires_at"]), needs_reauth,
                    )
                    counts["accounts"] += 1

                for p in posts:
                    body = json.loads(p["body"]) if isinstance(p["body"], str) else {}
                    await conn.execute(
                        """INSERT INTO social_posts(
                               id, customer_slug, content, link, hashtags, account_ids, media, options,
                               status, scheduled_at, revision, approved_revision, attempts, last_error,
                               created_at, updated_at)
                           VALUES($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb,
                                  $9, $10, $11, $12, $13, $14, COALESCE($15, now()), COALESCE($16, now()))
                           ON CONFLICT (id) DO NOTHING""",
                        p["id"],
                        p["customer_id"],
                        str(body.get("content") or ""),
                        str(body.get("link") or ""),
                        str(body.get("hashtags") or ""),
                        json.dumps(body.get("account_ids") or []),
                        json.dumps(body.get("media") or []),
                        json.dumps(body.get("options") or {}),
                        p["status"] or "draft",
                        _ts(p["scheduled_at"]),
                        int(p["revision"] or 1),
                        int(p["approved_revision"]) if p["approved_revision"] is not None else None,
                        int(body.get("attempts") or 0),
                        body.get("last_error"),
                        _ts(body.get("created_at")),
                        _ts(body.get("updated_at")),
                    )
                    counts["posts"] += 1

                for ap in approvals:
                    await conn.execute(
                        """INSERT INTO social_approvals(
                               token_hash, customer_slug, post_id, revision, scheduled_at, expires_at, used)
                           VALUES($1, $2, $3, $4, $5, COALESCE($6, now()), $7)
                           ON CONFLICT (token_hash) DO NOTHING""",
                        ap["token_hash"], ap["customer_id"], ap["post_id"], int(ap["revision"] or 1),
                        _ts(ap["scheduled_at"]), _ts(ap["expires_at"]), bool(ap["used"]),
                    )
                    counts["approvals"] += 1

                for r in results:
                    await conn.execute(
                        """INSERT INTO social_post_results(
                               post_id, account_id, external_post_id, error, ok, at)
                           VALUES($1, $2, $3, $4, $5, COALESCE($6, now()))
                           ON CONFLICT (post_id, account_id, ok) DO NOTHING""",
                        r["post_id"], r["account_id"], r["external_post_id"],
                        r["error"], bool(r["ok"]), _ts(r["at"]),
                    )
                    counts["post_results"] += 1

                for ev in events:
                    await conn.execute(
                        """INSERT INTO social_events(at, customer_slug, post_id, kind, detail)
                           VALUES(COALESCE($1, now()), $2, $3, $4, $5)""",
                        _ts(ev["at"]), ev["customer_id"], ev["post_id"], ev["kind"] or "event", ev["detail"] or "",
                    )
                    counts["events"] += 1
    finally:
        sconn.close()
    return counts


async def _main() -> None:
    sqlite_path = os.environ.get("LEGACY_SOCIAL_DB", "/backups/social-legacy-migrate.db")
    vault_key = os.environ.get("SOCIAL_VAULT_KEY", "").strip()
    dry_run = "--dry-run" in sys.argv
    if not Path(sqlite_path).is_file():
        raise SystemExit(f"Legacy social DB not found at {sqlite_path}")
    if not vault_key:
        raise SystemExit("SOCIAL_VAULT_KEY is required to decrypt legacy social tokens")
    if not dry_run:
        await db.init()
    try:
        counts = await migrate_sqlite_to_postgres(sqlite_path, vault_key, dry_run=dry_run)
        print(json.dumps(counts))
    finally:
        if not dry_run:
            await db.close()


if __name__ == "__main__":
    asyncio.run(_main())
