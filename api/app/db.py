from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

from . import rls
from .config import get_settings

_pool: asyncpg.Pool | None = None

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


@asynccontextmanager
async def tenant_conn(tenant_id):
    """Acquire a DB connection inside a transaction with Postgres RLS pinned to `tenant_id`."""
    async with pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            yield conn


async def init() -> None:
    """Create the connection pool and apply the (idempotent) schema + RLS tenant walls."""
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    schema = SCHEMA_PATH.read_text().replace("__DIM__", str(settings.embed_dim))
    async with _pool.acquire() as conn:
        await conn.execute(schema)
        await conn.execute(rls.rls_migration_sql())


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
