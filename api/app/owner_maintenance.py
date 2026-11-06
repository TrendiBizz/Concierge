"""Bounded retention maintenance for owner authentication records.

Invoke only from an explicitly configured scheduler/operations job. This module
never runs automatically at import or API startup, and does not send messages.
"""
import argparse
import asyncio
import json
import os

import asyncpg


async def prune_expired(conn: asyncpg.Connection, *, batch_size: int = 500,
                        dry_run: bool = True) -> dict[str, int]:
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    tables = {
        "tenant_sessions": "expires_at <= now()",
        "tenant_invites": "expires_at <= now() OR used_at IS NOT NULL",
        "owner_login_limits": "window_until <= now()",
    }
    result = {}
    async with conn.transaction():
        for table, predicate in tables.items():
            # Table and predicate are constants above, never user supplied.
            if dry_run:
                result[table] = await conn.fetchval(
                    f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {predicate} LIMIT $1) AS candidates",
                    batch_size,
                )
            else:
                rows = await conn.fetch(
                    f"DELETE FROM {table} WHERE ctid IN ("
                    f"SELECT ctid FROM {table} WHERE {predicate} "
                    f"LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING 1",
                    batch_size,
                )
                result[table] = len(rows)
    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded owner auth retention cleanup")
    parser.add_argument("--apply", action="store_true", help="delete eligible rows; default is dry run")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000:
        parser.error("--batch-size must be 1..5000")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL is required; no implicit production DB selection")
    conn = await asyncpg.connect(dsn)
    try:
        result = await prune_expired(conn, batch_size=args.batch_size, dry_run=not args.apply)
    finally:
        await conn.close()
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", "eligible": result}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
