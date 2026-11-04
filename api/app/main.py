import html
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from . import db, ingest, llm, tenants, voice
from .config import get_settings
from .rag import build_system_prompt, retrieve
from .security import RateLimiter, require_admin
from .tools import chat_tools, run_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("concierge")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_TOOL_ROUNDS = 3

settings = get_settings()
ip_limiter = RateLimiter(settings.chat_rate_per_minute_ip, 60)
session_limiter = RateLimiter(settings.chat_rate_per_day_session, 86_400)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init()
    yield
    await db.close()


app = FastAPI(title="Website AI Concierge", lifespan=lifespan)

# Public widget endpoints authenticate with the tenant's public key in the request body, not
# cookies, so wildcard CORS is safe. Per-tenant origin allow-lists are enforced in code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


# ------------------------------------------------------------------ helpers
def _clean_utm(utm: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (utm or {}).items():
        if key.startswith("utm_") and len(out) < 10:
            out[key[:40]] = str(value)[:200]
    return out


def _clean_session(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64]
    if len(cleaned) < 8:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    return cleaned


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


async def _tenant_for(request: Request, key: str) -> dict:
    tenant = await tenants.get_by_key(key)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown key")
    origin = request.headers.get("origin")
    allowed = tenant["allowed_origins"]
    if allowed and origin:
        permitted = {o.rstrip("/").lower() for o in allowed}
        permitted.add(_origin_of(settings.public_base_url))  # our own /demo pages
        if origin.rstrip("/").lower() not in permitted:
            raise HTTPException(status_code=403, detail="Origin not allowed")
    return tenant


def _rate_limit(request: Request, session_id: str | None = None) -> None:
    ip = request.client.host if request.client else "unknown"
    if not ip_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Too many requests, please slow down")
    if session_id and not session_limiter.check(session_id):
        raise HTTPException(status_code=429, detail="Session limit reached")


async def _conversation(tenant: dict, session_id: str, channel: str, page_url: str | None, utm: dict) -> str:
    row = await db.pool().fetchrow(
        """
        INSERT INTO conversations (tenant_id, session_id, channel, page_url, utm)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (tenant_id, session_id, channel)
        DO UPDATE SET page_url = COALESCE(conversations.page_url, EXCLUDED.page_url)
        RETURNING id
        """,
        tenant["id"],
        session_id,
        channel,
        (page_url or "")[:500] or None,
        json.dumps(_clean_utm(utm)),
    )
    return row["id"]


async def _save_message(conversation_id, role: str, content: str) -> None:
    await db.pool().execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES ($1, $2, $3)",
        conversation_id,
        role,
        content[:4000],
    )


# ------------------------------------------------------------- public API
@app.get("/healthz")
async def healthz():
    await db.pool().fetchval("SELECT 1")
    return {"ok": True}


@app.get("/widget.js")
async def widget_js():
    return FileResponse(
        STATIC_DIR / "widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/api/v1/widget-config")
async def widget_config(request: Request, key: str):
    tenant = await _tenant_for(request, key)
    return tenants.public_view(tenant)


class ChatRequest(BaseModel):
    key: str
    session_id: str
    message: str = Field(min_length=1, max_length=1000)
    page_url: str | None = None
    utm: dict[str, str] = {}


@app.post("/api/v1/chat")
async def chat(req: ChatRequest, request: Request):
    session_id = _clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await _conversation(tenant, session_id, "chat", req.page_url, req.utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": "chat",
        "page_url": req.page_url,
        "utm": _clean_utm(req.utm),
    }

    history = await db.pool().fetch(
        """
        SELECT role, content FROM (
            SELECT id, role, content FROM messages WHERE conversation_id = $1 ORDER BY id DESC LIMIT 10
        ) recent ORDER BY id
        """,
        conversation_id,
    )
    await _save_message(conversation_id, "user", req.message)

    try:
        hits = await retrieve(tenant["id"], req.message)
        messages: list[dict] = [{"role": "system", "content": build_system_prompt(tenant, hits, "chat")}]
        messages += [{"role": r["role"], "content": r["content"]} for r in history]
        messages.append({"role": "user", "content": req.message})

        reply = ""
        for _ in range(MAX_TOOL_ROUNDS):
            msg = await llm.complete(messages, tools=chat_tools())
            if not msg.tool_calls:
                reply = (msg.content or "").strip()
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await run_tool(tenant, tc.function.name, args, ctx)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
        if not reply:
            reply = "Sorry, I had trouble with that. Could you rephrase, or leave your phone number or email so the team can follow up?"
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed for tenant %s", tenant["slug"])
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable")

    await _save_message(conversation_id, "assistant", reply)
    return {
        "reply": reply,
        "lead_captured": bool(ctx.get("lead_captured")),
        "booking_url": ctx.get("booking_url"),
    }


class VoiceTokenRequest(BaseModel):
    key: str
    session_id: str


@app.post("/api/v1/voice/token")
async def voice_token(req: VoiceTokenRequest, request: Request):
    session_id = _clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    try:
        return await voice.mint_token(tenant)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Voice service unreachable")


class ToolRequest(BaseModel):
    key: str
    session_id: str
    args: dict = {}
    page_url: str | None = None
    utm: dict[str, str] = {}


@app.post("/api/v1/tools/{name}")
async def tool_endpoint(name: str, req: ToolRequest, request: Request):
    """Called by the widget when Grok Voice invokes a function."""
    session_id = _clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await _conversation(tenant, session_id, "voice", req.page_url, req.utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": "voice",
        "page_url": req.page_url,
        "utm": _clean_utm(req.utm),
    }
    return await run_tool(tenant, name, req.args, ctx)


class VoiceLogRequest(BaseModel):
    key: str
    session_id: str
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=4000)
    page_url: str | None = None
    utm: dict[str, str] = {}


@app.post("/api/v1/voice/log")
async def voice_log(req: VoiceLogRequest, request: Request):
    session_id = _clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await _conversation(tenant, session_id, "voice", req.page_url, req.utm)
    await _save_message(conversation_id, req.role, req.text)
    return {"ok": True}


# -------------------------------------------------------------- demo page
@app.get("/demo/{slug}", response_class=HTMLResponse)
async def demo_page(slug: str, presenter: int = 0):
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown demo")

    excerpt = await db.pool().fetchval(
        "SELECT content FROM chunks WHERE tenant_id = $1 ORDER BY id LIMIT 1", tenant["id"]
    )
    name = html.escape(tenant["name"])
    excerpt_html = html.escape((excerpt or "")[:700]).replace("\n", "<br>")
    site = tenant.get("site_url") or ""
    site_html = html.escape(site) if site.startswith(("http://", "https://")) else ""

    questions = tenant["demo_questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    panel = ""
    if presenter and questions:
        items = "".join(f"<li>{html.escape(q)}</li>" for q in questions)
        panel = f"<aside><h2>Questions to ask</h2><ol>{items}</ol></aside>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - AI guide demo</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;color:#111;background:#fafafa}}
 header{{padding:24px;background:{html.escape(tenant['accent_color'])};color:#fff}}
 main{{max-width:760px;margin:32px auto;padding:0 16px;line-height:1.6}}
 aside{{position:fixed;left:16px;bottom:16px;max-width:380px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;font-size:14px}}
 small{{color:#666}}
</style></head>
<body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">Sandbox preview of your AI guide{' - ' + site_html if site_html else ''}</small></header>
<main><p>{excerpt_html}</p></main>
{panel}
<script src="/widget.js" data-key="{html.escape(tenant['public_key'])}" data-autoopen="1" defer></script>
</body></html>"""
    return HTMLResponse(page)


# -------------------------------------------------------------------- admin
admin = [Depends(require_admin)]


class TenantCreate(BaseModel):
    name: str
    site_url: str | None = None
    slug: str | None = None
    persona: str = ""
    greeting: str = ""
    booking_url: str | None = None
    lead_webhook_url: str | None = None
    incentive: str = ""
    allowed_origins: list[str] = []


class TenantUpdate(BaseModel):
    name: str | None = None
    site_url: str | None = None
    allowed_origins: list[str] | None = None
    persona: str | None = None
    greeting: str | None = None
    cta_text: str | None = None
    accent_color: str | None = None
    voice: str | None = None
    voice_enabled: bool | None = None
    voice_daily_limit: int | None = None
    booking_url: str | None = None
    lead_webhook_url: str | None = None
    incentive: str | None = None


def _with_snippet(tenant: dict) -> dict:
    snippet = (
        f'<script src="{settings.public_base_url}/widget.js" data-key="{tenant["public_key"]}" defer></script>'
    )
    return {**tenant, "embed_snippet": snippet, "demo_url": f"{settings.public_base_url}/demo/{tenant['slug']}?presenter=1"}


async def _require_tenant(slug: str) -> dict:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


@app.post("/admin/tenants", dependencies=admin)
async def admin_create_tenant(body: TenantCreate):
    data = body.model_dump()
    tenant = await tenants.create(
        data.pop("name"), data.pop("site_url"), slug=data.pop("slug"), **data
    )
    return _with_snippet(tenant)


@app.get("/admin/tenants", dependencies=admin)
async def admin_list_tenants():
    return [_with_snippet(t) for t in await tenants.list_all()]


@app.get("/admin/tenants/{slug}", dependencies=admin)
async def admin_get_tenant(slug: str):
    tenant = await _require_tenant(slug)
    chunks = await db.pool().fetchval("SELECT count(*) FROM chunks WHERE tenant_id = $1", tenant["id"])
    return {**_with_snippet(tenant), "chunk_count": chunks}


@app.patch("/admin/tenants/{slug}", dependencies=admin)
async def admin_update_tenant(slug: str, body: TenantUpdate):
    await _require_tenant(slug)
    updated = await tenants.update(slug, body.model_dump(exclude_unset=True))
    return _with_snippet(updated)


@app.delete("/admin/tenants/{slug}", dependencies=admin)
async def admin_delete_tenant(slug: str):
    if not await tenants.delete(slug):
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return {"ok": True}


class CrawlRequest(BaseModel):
    max_pages: int = Field(default=40, ge=1, le=300)


async def _crawl_job(tenant: dict, max_pages: int) -> None:
    try:
        await ingest.ingest_site(tenant, max_pages=max_pages)
    except Exception:
        log.exception("crawl failed for %s", tenant["slug"])


@app.post("/admin/tenants/{slug}/crawl", dependencies=admin, status_code=202)
async def admin_crawl(slug: str, body: CrawlRequest, background: BackgroundTasks):
    tenant = await _require_tenant(slug)
    if not tenant.get("site_url"):
        raise HTTPException(status_code=400, detail="Tenant has no site_url")
    background.add_task(_crawl_job, tenant, body.max_pages)
    return {"status": "started", "hint": "Check chunk_count on GET /admin/tenants/{slug}"}


class IngestTextRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80, pattern="^[A-Za-z0-9_.-]+$")
    title: str = ""
    text: str = Field(min_length=1, max_length=200_000)


@app.post("/admin/tenants/{slug}/ingest-text", dependencies=admin)
async def admin_ingest_text(slug: str, body: IngestTextRequest):
    tenant = await _require_tenant(slug)
    return await ingest.ingest_text(tenant, body.label, body.text, body.title)


@app.post("/admin/tenants/{slug}/demo-questions", dependencies=admin)
async def admin_demo_questions(slug: str):
    tenant = await _require_tenant(slug)
    try:
        return {"questions": await ingest.generate_demo_questions(tenant)}
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")


@app.get("/admin/tenants/{slug}/leads", dependencies=admin)
async def admin_leads(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM leads WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2",
        tenant["id"],
        min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.get("/admin/tenants/{slug}/conversations", dependencies=admin)
async def admin_conversations(slug: str, limit: int = 50):
    """Recent conversations with their transcripts - review these monthly to improve the knowledge base."""
    tenant = await _require_tenant(slug)
    convs = await db.pool().fetch(
        "SELECT * FROM conversations WHERE tenant_id = $1 ORDER BY started_at DESC LIMIT $2",
        tenant["id"],
        min(max(limit, 1), 200),
    )
    out = []
    for conv in convs:
        msgs = await db.pool().fetch(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = $1 ORDER BY id",
            conv["id"],
        )
        out.append({**dict(conv), "messages": [dict(m) for m in msgs]})
    return out


@app.get("/admin/tenants/{slug}/stats", dependencies=admin)
async def admin_stats(slug: str, days: int = 30):
    tenant = await _require_tenant(slug)
    days = min(max(days, 1), 365)
    pool = db.pool()
    convs = await pool.fetch(
        """
        SELECT channel, count(*) AS conversations
        FROM conversations
        WHERE tenant_id = $1 AND started_at > now() - make_interval(days => $2)
        GROUP BY channel
        """,
        tenant["id"],
        days,
    )
    leads = await pool.fetchval(
        "SELECT count(*) FROM leads WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)",
        tenant["id"],
        days,
    )
    daily = await pool.fetch(
        """
        SELECT d::date AS day,
               (SELECT count(*) FROM conversations c WHERE c.tenant_id = $1 AND c.started_at::date = d::date) AS conversations,
               (SELECT count(*) FROM leads l WHERE l.tenant_id = $1 AND l.created_at::date = d::date) AS leads
        FROM generate_series(now() - make_interval(days => $2 - 1), now(), interval '1 day') d
        ORDER BY day
        """,
        tenant["id"],
        days,
    )
    total_convs = sum(r["conversations"] for r in convs)
    return {
        "days": days,
        "conversations": total_convs,
        "by_channel": {r["channel"]: r["conversations"] for r in convs},
        "leads": leads,
        "lead_rate": round(leads / total_convs, 3) if total_convs else 0,
        "daily": [dict(r) for r in daily],
    }
