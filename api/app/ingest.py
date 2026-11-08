import json
import logging

from . import db, llm
from .chunking import chunk_text
from .crawler import Page, crawl
from .embeddings import embed_documents, to_pgvector

log = logging.getLogger("concierge.ingest")

MANUAL_PREFIX = "manual:"


async def _store(tenant_id, pages: list[Page], replace_crawled: bool,
                 replace_url: str | None = None) -> int:
    records: list[tuple[str, str, str]] = []
    for page in pages:
        for chunk in chunk_text(page.text):
            # Prefix the title so short chunks still carry their page context.
            text = f"{page.title}\n\n{chunk}" if page.title else chunk
            records.append((page.url, page.title, text))
    if not records:
        return 0

    # Embed first so a failure here never wipes the existing knowledge base.
    vectors = await embed_documents([r[2] for r in records])
    if len(vectors) != len(records):
        raise RuntimeError("Incomplete document embeddings")

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if replace_url is not None:
                # Serialize replacement of one customer's document. Embed first,
                # then replace in this transaction so failures retain saved data.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"knowledge:{tenant_id}:{replace_url}",
                )
                await conn.execute("DELETE FROM chunks WHERE tenant_id=$1 AND url=$2",
                                   tenant_id, replace_url)
            if replace_crawled:
                await conn.execute(
                    "DELETE FROM chunks WHERE tenant_id = $1 AND url NOT LIKE $2",
                    tenant_id,
                    MANUAL_PREFIX + "%",
                )
            await conn.executemany(
                "INSERT INTO chunks (tenant_id, url, title, content, embedding) "
                "VALUES ($1, $2, $3, $4, $5::text::vector)",
                [
                    (tenant_id, url, title, text, to_pgvector(vec))
                    for (url, title, text), vec in zip(records, vectors)
                ],
            )
    return len(records)


async def ingest_site(tenant: dict, max_pages: int = 40) -> dict:
    site_url = tenant.get("site_url")
    if not site_url:
        raise ValueError("Tenant has no site_url")
    pages = await crawl(site_url, max_pages=max_pages)
    chunks = await _store(tenant["id"], pages, replace_crawled=True)
    log.info("ingested %s: %d pages, %d chunks", tenant["slug"], len(pages), chunks)
    return {"pages": len(pages), "chunks": chunks}


async def ingest_text(tenant: dict, label: str, text: str, title: str = "") -> dict:
    """Add hand-written knowledge (price lists, FAQs). Survives re-crawls."""
    url = f"{MANUAL_PREFIX}{label}"
    chunks = await _store(tenant["id"], [Page(url=url, title=title or label, text=text)],
                          replace_crawled=False, replace_url=url)
    return {"chunks": chunks}


async def generate_demo_questions(tenant: dict, count: int = 5) -> list[str]:
    """Ask the LLM for questions that will show off this specific business in a live demo."""
    rows = await db.pool().fetch(
        "SELECT title, content FROM chunks WHERE tenant_id = $1 ORDER BY id LIMIT 14", tenant["id"]
    )
    if not rows:
        return []
    sample = "\n\n".join(f"{r['title']}\n{r['content']}" for r in rows)[:7000]
    message = await llm.complete(
        [
            {
                "role": "system",
                "content": (
                    "You prepare live demos of a website AI assistant. Given a business's website "
                    f"content, write {count} realistic, specific questions a customer might ask that "
                    "this content can answer and that would impress the owner (niche specialties, "
                    "pricing, compatibility, edge cases). One question per line, no numbering, "
                    "no extra text."
                ),
            },
            {"role": "user", "content": f"Business: {tenant['name']}\n\n{sample}"},
        ],
        temperature=0.7,
        max_tokens=400,
    )
    questions = [
        line.strip(" -•\t0123456789.").strip()
        for line in (message.content or "").splitlines()
        if line.strip()
    ][:count]
    await db.pool().execute(
        "UPDATE tenants SET demo_questions = $2::jsonb WHERE id = $1",
        tenant["id"],
        json.dumps(questions),
    )
    return questions
