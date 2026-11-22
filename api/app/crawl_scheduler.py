"""N13 Knowledge Base upload (PDF/DOCX/TXT/MD), RAG thresholds, and scheduled re-crawl worker."""
from __future__ import annotations

import asyncio
import base64
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db, doc_extract, ingest, owner_auth, tenants

log = logging.getLogger("concierge.crawl_scheduler")
router = APIRouter(prefix="/owner/knowledge", tags=["knowledge-n13"])


@router.post("/upload", status_code=201)
async def upload_knowledge_document(
    request: Request,
    user: dict = Depends(owner_auth.current_user),
):
    """Upload a PDF, DOCX, TXT, or MD document directly into the tenant's knowledge base.

    Accepts either raw file bytes with `X-Filename` (and optional `X-Title`) headers, or JSON
    `{"filename": "...", "content_base64": "...", "title": "..."}`. Avoids python-multipart.
    """
    owner_auth.require_role(user, "editor")
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        body = await request.json()
        filename = str(body.get("filename") or "document.txt").strip()
        title = str(body.get("title") or "").strip()
        b64 = str(body.get("content_base64") or "")
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception:
            raise HTTPException(400, "Invalid base64 file content") from None
    else:
        filename = (request.headers.get("x-filename") or "document.txt").strip()
        title = (request.headers.get("x-title") or "").strip()
        data = await request.body()
    if len(data) > doc_extract.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 10 MB limit")
    try:
        text = doc_extract.extract_document(filename, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    tenant = await tenants.get_by_id(user["tenant_id"])
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    safe_label = re.sub(r"[^a-z0-9._-]+", "-", filename.lower()).strip("-") or "upload"
    doc_title = (title or filename).strip()[:200]
    res = await ingest.ingest_text(tenant, label=f"doc:{safe_label}", text=text, title=doc_title)
    return {
        "url": f"{ingest.MANUAL_PREFIX}doc:{safe_label}",
        "title": doc_title,
        "chunks": res["chunks"],
        "chars": len(text),
    }


class KnowledgeScheduleUpdate(BaseModel):
    crawl_interval_hours: int = Field(ge=0, le=720)
    rag_min_score: float = Field(default=0.25, ge=0.0, le=0.95)


@router.get("/schedule")
async def get_knowledge_schedule(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT site_url, crawl_interval_hours, last_crawled_at, rag_min_score FROM tenants WHERE id=$1",
        user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Tenant not found")
    return {
        "site_url": row["site_url"] or "",
        "crawl_interval_hours": int(row["crawl_interval_hours"] or 0),
        "last_crawled_at": row["last_crawled_at"].isoformat() if row["last_crawled_at"] else None,
        "rag_min_score": float(row["rag_min_score"] if row["rag_min_score"] is not None else 0.25),
    }


@router.put("/schedule")
async def set_knowledge_schedule(body: KnowledgeScheduleUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    await db.pool().execute(
        "UPDATE tenants SET crawl_interval_hours=$2, rag_min_score=$3 WHERE id=$1",
        user["tenant_id"], body.crawl_interval_hours, body.rag_min_score,
    )
    return {
        "crawl_interval_hours": body.crawl_interval_hours,
        "rag_min_score": body.rag_min_score,
    }


async def run_due_crawls(limit: int = 5) -> int:
    """Re-crawl tenants whose scheduled crawl interval has elapsed. Returns tenants crawled."""
    rows = await db.pool().fetch(
        "SELECT * FROM tenants WHERE crawl_interval_hours > 0 AND site_url <> '' "
        "AND (last_crawled_at IS NULL OR last_crawled_at < now() - make_interval(hours => crawl_interval_hours)) "
        "ORDER BY last_crawled_at ASC NULLS FIRST LIMIT $1",
        limit,
    )
    crawled = 0
    for row in rows:
        tenant = dict(row)
        try:
            await ingest.ingest_site(tenant)
            await db.pool().execute("UPDATE tenants SET last_crawled_at=now() WHERE id=$1", tenant["id"])
            crawled += 1
        except Exception:
            log.warning("Scheduled re-crawl failed for %s", tenant.get("slug"))
    return crawled


async def run_forever(stop: asyncio.Event, interval_seconds: int = 1800) -> None:
    while not stop.is_set():
        try:
            await run_due_crawls()
        except Exception:
            log.warning("Scheduled re-crawl sweep will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
