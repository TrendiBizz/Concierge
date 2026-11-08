"""Bounded, tenant-scoped business documents; no URL fetching or activation."""
import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db, ingest, tenants

PREFIX = "manual:owner:"
DOCUMENT_ID = re.compile(r"^[0-9a-f]{64}$")


class BusinessDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=100_000)

    @field_validator("title", "text")
    @classmethod
    def plain_text(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not value or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Enter readable business information")
        if len(value.encode("utf-8")) > 100_000:
            raise ValueError("Document must be no larger than 100 KB")
        return value


async def documents(tenant_id) -> list[dict]:
    rows = await db.pool().fetch(
        "SELECT url, min(title) AS title, count(*) AS chunks "
        "FROM chunks WHERE tenant_id=$1 AND url LIKE $2 GROUP BY url ORDER BY min(title)",
        tenant_id, PREFIX + "%",
    )
    return [{"document_id": row["url"][len(PREFIX):], "title": row["title"],
             "chunks": row["chunks"]} for row in rows]


async def save(tenant_id, document: BusinessDocument) -> dict:
    tenant = await tenants.get_by_id(tenant_id)
    if tenant is None:
        raise ValueError("Business unavailable")
    identity = hashlib.sha256(document.title.casefold().encode()).hexdigest()
    result = await ingest.ingest_text(tenant, "owner:" + identity,
                                      document.text, title=document.title)
    return {"document_id": identity, "title": document.title, "chunks": result["chunks"]}


async def remove(tenant_id, document_id: str) -> bool:
    if not DOCUMENT_ID.fullmatch(document_id):
        return False
    url = PREFIX + document_id
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                               f"knowledge:{tenant_id}:{url}")
            deleted = await conn.fetchval(
                "WITH deleted AS (DELETE FROM chunks WHERE tenant_id=$1 AND url=$2 RETURNING id) "
                "SELECT count(*) FROM deleted", tenant_id, url,
            )
    return bool(deleted)
