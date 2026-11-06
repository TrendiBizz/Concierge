"""Isolated verification for owner retention maintenance. Disposable DB only."""
import asyncio
import os

os.environ["DATABASE_URL"] = "postgresql://postgres:test@127.0.0.1:55432/postgres"
os.environ["OUTBOX_ENABLED"] = "false"

from app import db
from app.owner_maintenance import prune_expired


async def run():
    await db.init()
    try:
        async with db.pool().acquire() as conn:
            await conn.execute("DELETE FROM owner_login_limits")
            await conn.execute("INSERT INTO owner_login_limits(key_hash,attempts,window_until) VALUES ('expired-maintenance',3,now()-interval '1 day'),('active-maintenance',2,now()+interval '1 day')")
            preview = await prune_expired(conn, dry_run=True)
            assert preview == {"tenant_sessions": 0, "tenant_invites": 0, "owner_login_limits": 1}, preview
            assert await conn.fetchval("SELECT count(*) FROM owner_login_limits") == 2
            applied = await prune_expired(conn, dry_run=False)
            assert applied == preview, applied
            assert await conn.fetchval("SELECT count(*) FROM owner_login_limits") == 1
            assert await conn.fetchval("SELECT key_hash FROM owner_login_limits") == "active-maintenance"
            again = await prune_expired(conn, dry_run=False)
            assert not any(again.values()), again
            for invalid in (0, 5001):
                try:
                    await prune_expired(conn, batch_size=invalid)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Expected invalid batch size rejection")
        print("7/7 owner maintenance checks passed")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())
