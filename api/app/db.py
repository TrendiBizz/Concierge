from pathlib import Path

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


async def init() -> None:
    """Create the connection pool and apply the (idempotent) schema."""
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    schema = SCHEMA_PATH.read_text().replace("__DIM__", str(settings.embed_dim))
    async with _pool.acquire() as conn:
        await conn.execute(schema)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
