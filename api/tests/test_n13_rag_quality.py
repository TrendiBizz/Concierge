"""N13 RAG Quality & Knowledge Completeness tests:
- PDF & DOCX document extraction and upload endpoint
- Hybrid search (dense + Postgres tsvector RRF) and relevance threshold filtering
- Scheduled re-crawl settings and due-tenant execution
"""
from __future__ import annotations

import asyncio
import io
import os
import pathlib
import zipfile

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import crawl_scheduler, db, doc_extract, ingest, owner_auth, rag, tenants
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
    db._pool = pool
    return pool


def run(fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


def _make_docx(text: str) -> bytes:
    buf = io.BytesIO()
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _make_minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    return (
        b"%PDF-1.4\n1 0 obj << /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n%%EOF\n"
    )


def test_pdf_and_docx_extractors():
    docx_bytes = _make_docx("Roofing price list NZD 125 per square metre SKU-RF900")
    assert "SKU-RF900" in doc_extract.extract_document("prices.docx", docx_bytes)

    pdf_bytes = _make_minimal_pdf("Warranty terms 10 years Auckland North Shore")
    assert "Auckland North Shore" in doc_extract.extract_document("warranty.pdf", pdf_bytes)

    with pytest.raises(ValueError):
        doc_extract.extract_document("malware.exe", b"MZ1234567890")


def test_hybrid_rrf_fusion_and_threshold():
    dense = [
        {"url": "https://a/irrelevant", "title": "Blog", "content": "Unrelated chatter", "score": 0.12},
        {"url": "https://a/general", "title": "About", "content": "We do plumbing", "score": 0.45},
    ]
    lexical = [
        {"url": "https://a/sku", "title": "Catalog", "content": "Part SKU-9941 valve", "lex_score": 0.9},
    ]
    hits = rag.fuse_hybrid_hits(dense, lexical, k=5, min_score=0.25)
    urls = [h["url"] for h in hits]
    assert "https://a/irrelevant" not in urls  # filtered below 0.25 threshold
    assert "https://a/sku" in urls             # lexical SKU match preserved
    assert "https://a/general" in urls


@needs_db
def test_upload_docx_hybrid_retrieve_and_scheduled_recrawl(monkeypatch):
    async def fake_embed_docs(texts):
        return [[0.1] * 384 for _ in texts]

    async def fake_embed_query(q):
        return [0.1] * 384

    monkeypatch.setattr(ingest, "embed_documents", fake_embed_docs)
    monkeypatch.setattr(rag, "embed_query", fake_embed_query)

    async def _go(pool):
        t = await tenants.create("RAG Co", "https://ragco.example", "rag-co")
        inv = await owner_auth.make_invite(t["id"], "owner@ragco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Upload DOCX document into knowledge base
            docx_bytes = _make_docx("Our special pump model is PUMPKIN-7742 stocked in Tauranga.")
            up = await client.post(
                "/owner/knowledge/upload",
                headers={**headers, "X-Filename": "catalog.docx", "X-Title": "Pump Catalog"},
                content=docx_bytes,
            )
            assert up.status_code == 201
            assert up.json()["chunks"] >= 1

            # 2. Hybrid search finds exact SKU via tsvector + pgvector
            hits = await rag.retrieve(t["id"], "PUMPKIN-7742 Tauranga", k=4)
            assert any("PUMPKIN-7742" in h["content"] for h in hits)

            # 3. Schedule settings & due re-crawl worker
            sch = await client.put("/owner/knowledge/schedule", headers=headers, json={"crawl_interval_hours": 24, "rag_min_score": 0.3})
            assert sch.status_code == 200 and sch.json()["crawl_interval_hours"] == 24

            crawled_slugs = []
            async def fake_ingest_site(tenant, max_pages=40):
                crawled_slugs.append(tenant["slug"])
                return {"pages": 1, "chunks": 2}
            monkeypatch.setattr(ingest, "ingest_site", fake_ingest_site)

            n = await crawl_scheduler.run_due_crawls()
            assert n == 1 and crawled_slugs == ["rag-co"]
            # Second run immediately after should skip because last_crawled_at is now fresh
            assert await crawl_scheduler.run_due_crawls() == 0
    run(_go)
