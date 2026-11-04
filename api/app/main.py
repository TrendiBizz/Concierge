import asyncio
import html
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import automation, chat as chat_engine, convo, db, ingest, llm, outbox, sms, tenants, voice
from .booking import DAYS
from .config import get_settings
from .contact import normalize_phone
from .security import RateLimiter, require_admin
from .tools import run_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("concierge")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

settings = get_settings()
ip_limiter = RateLimiter(settings.chat_rate_per_minute_ip, 60)
session_limiter = RateLimiter(settings.chat_rate_per_day_session, 86_400)
sms_limiter = RateLimiter(30, 3600)

LEAD_STATUSES = ("new", "contacted", "booked", "won", "lost")
APPT_STATUSES = ("booked", "completed", "cancelled", "no_show")
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
START_WORDS = {"START", "UNSTOP"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init()
    await tenants.ensure_report_tokens()
    stop = asyncio.Event()
    worker = asyncio.create_task(outbox.run_forever(stop)) if settings.outbox_enabled else None
    yield
    stop.set()
    if worker:
        await worker
    await db.close()


app = FastAPI(title="Website AI Concierge", lifespan=lifespan)

# Public widget endpoints authenticate with the tenant's public key in the request body, not
# cookies, so wildcard CORS is safe. Per-tenant origin allow-lists are enforced in code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


# ------------------------------------------------------------------ helpers
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
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    try:
        result = await chat_engine.run_turn(
            tenant, session_id, "chat", req.message, page_url=req.page_url, utm=req.utm
        )
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed for tenant %s", tenant["slug"])
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable")
    return {
        "reply": result["reply"],
        "lead_captured": result["lead_captured"],
        "booking_url": result["booking_url"],
        "appointment": result["appointment"],
    }


def _twiml(text: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response>'
    if text:
        body += f"<Message>{xml_escape(text[:1500])}</Message>"
    body += "</Response>"
    return Response(content=body, media_type="application/xml")


@app.post("/api/v1/sms/{public_key}")
async def sms_inbound(public_key: str, request: Request):
    """Twilio inbound-SMS webhook: a visitor texts the client's number and the AI replies."""
    tenant = await tenants.get_by_key(public_key)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown key")
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="SMS is not configured")

    raw = (await request.body()).decode("utf-8", errors="replace")
    params = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
    url = settings.public_base_url.rstrip("/") + request.url.path
    if not sms.validate_signature(settings.twilio_auth_token, url, params, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="Invalid signature")

    sender = normalize_phone(params.get("From", ""), settings.default_country_code)
    body = (params.get("Body") or "").strip()
    if not sender or not body:
        return _twiml("")

    command = body.upper()
    if command in STOP_WORDS:
        await outbox.opt_out(tenant["id"], sender)
        return _twiml("")  # Twilio sends its own opt-out confirmation
    if command in START_WORDS:
        await outbox.opt_in(tenant["id"], sender)
        return _twiml(f"You're subscribed to messages from {tenant['name']} again. Reply STOP to opt out.")
    if command == "HELP":
        return _twiml(f"{tenant['name']} AI assistant. Msg&data rates may apply. Reply STOP to opt out.")
    if await outbox.is_opted_out(tenant["id"], sender):
        return _twiml("")

    session_id = "sms" + re.sub(r"\D", "", sender)
    if not sms_limiter.check(session_id):
        return _twiml("")
    try:
        result = await chat_engine.run_turn(tenant, session_id, "sms", body[:1000], sender_phone=sender)
    except Exception:
        log.exception("sms turn failed for %s", tenant["slug"])
        return _twiml("Sorry, I'm having trouble right now. The team will get back to you.")
    return _twiml(result["reply"])


class VoiceTokenRequest(BaseModel):
    key: str
    session_id: str


@app.post("/api/v1/voice/token")
async def voice_token(req: VoiceTokenRequest, request: Request):
    session_id = convo.clean_session(req.session_id)
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
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await convo.get_or_create(tenant, session_id, "voice", req.page_url, req.utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": "voice",
        "page_url": req.page_url,
        "utm": convo.clean_utm(req.utm),
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
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await convo.get_or_create(tenant, session_id, "voice", req.page_url, req.utm)
    await convo.save_message(conversation_id, "user" if req.role == "user" else "assistant", req.text)
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


# ------------------------------------------------------------ client report
async def _stats(tenant: dict, days: int) -> dict:
    pool = db.pool()
    days = min(max(days, 1), 365)
    convs = await pool.fetch(
        """
        SELECT channel, count(*) AS conversations
        FROM conversations
        WHERE tenant_id = $1 AND channel <> 'eval' AND started_at > now() - make_interval(days => $2)
        GROUP BY channel
        """,
        tenant["id"], days,
    )
    leads_by_status = await pool.fetch(
        "SELECT status, count(*) AS n FROM leads WHERE tenant_id = $1 "
        "AND created_at > now() - make_interval(days => $2) GROUP BY status",
        tenant["id"], days,
    )
    appointments = await pool.fetchval(
        "SELECT count(*) FROM appointments WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)",
        tenant["id"], days,
    )
    guard_hits = await pool.fetchval(
        """
        SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id
        WHERE c.tenant_id = $1 AND m.flag = 'quote_guard' AND m.created_at > now() - make_interval(days => $2)
        """,
        tenant["id"], days,
    )
    sent = await pool.fetch(
        "SELECT channel, count(*) AS n FROM outbox WHERE tenant_id = $1 AND status = 'sent' "
        "AND created_at > now() - make_interval(days => $2) GROUP BY channel",
        tenant["id"], days,
    )
    daily = await pool.fetch(
        """
        SELECT d::date AS day,
               (SELECT count(*) FROM conversations c WHERE c.tenant_id = $1 AND c.channel <> 'eval' AND c.started_at::date = d::date) AS conversations,
               (SELECT count(*) FROM leads l WHERE l.tenant_id = $1 AND l.created_at::date = d::date) AS leads
        FROM generate_series(now() - make_interval(days => $2 - 1), now(), interval '1 day') d
        ORDER BY day
        """,
        tenant["id"], days,
    )
    status_counts = {r["status"]: r["n"] for r in leads_by_status}
    total_leads = sum(status_counts.values())
    total_convs = sum(r["conversations"] for r in convs)
    value_each = tenant.get("lead_value_cents") or 0
    won_value = await pool.fetchval(
        "SELECT COALESCE(sum(value_cents), 0) FROM leads WHERE tenant_id = $1 AND status = 'won' "
        "AND updated_at > now() - make_interval(days => $2)",
        tenant["id"], days,
    )
    return {
        "days": days,
        "conversations": total_convs,
        "by_channel": {r["channel"]: r["conversations"] for r in convs},
        "leads": total_leads,
        "leads_by_status": status_counts,
        "lead_rate": round(total_leads / total_convs, 3) if total_convs else 0,
        "appointments": appointments,
        "estimated_pipeline_cents": total_leads * value_each,
        "won_value_cents": won_value,
        "quote_guard_interventions": guard_hits,
        "messages_sent": {r["channel"]: r["n"] for r in sent},
        "daily": [dict(r) for r in daily],
    }


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


@app.get("/report/{token}", response_class=HTMLResponse)
async def client_report(token: str, days: int = 30):
    """Read-only monthly report for the client. The unguessable token is the credential."""
    tenant = await tenants.get_by_report_token(token)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    s = await _stats(tenant, days)

    peak = max([d["leads"] for d in s["daily"]] + [d["conversations"] for d in s["daily"]] + [1])
    bar_w = 600 / max(len(s["daily"]), 1)
    bars = []
    for i, d in enumerate(s["daily"]):
        x = i * bar_w
        h_c = 100 * d["conversations"] / peak
        h_l = 100 * d["leads"] / peak
        bars.append(
            f'<rect x="{x:.1f}" y="{110 - h_c:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_c:.1f}" fill="#94a3b8"/>'
            f'<rect x="{x + bar_w * 0.45:.1f}" y="{110 - h_l:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_l:.1f}" fill="{html.escape(tenant["accent_color"])}"/>'
        )
    leads = await db.pool().fetch(
        "SELECT name, message, channel, status, created_at FROM leads WHERE tenant_id = $1 "
        "AND created_at > now() - make_interval(days => $2) ORDER BY created_at DESC LIMIT 25",
        tenant["id"], s["days"],
    )
    rows = "".join(
        f"<tr><td>{r['created_at']:%b %d}</td><td>{html.escape((r['name'] or 'Visitor').split(' ')[0])}</td>"
        f"<td>{html.escape(r['message'][:140])}</td><td>{html.escape(r['channel'])}</td><td>{html.escape(r['status'])}</td></tr>"
        for r in leads
    )
    card = lambda label, value: f'<div class="c"><b>{value}</b><span>{label}</span></div>'  # noqa: E731
    cards = "".join([
        card("Visitor conversations", s["conversations"]),
        card("Leads captured", s["leads"]),
        card("Appointments booked", s["appointments"]),
        card("Estimated pipeline", _money(s["estimated_pipeline_cents"]) if s["estimated_pipeline_cents"] else "-"),
    ])
    name = html.escape(tenant["name"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{name} - AI guide report</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#111}}
 header{{background:{html.escape(tenant['accent_color'])};color:#fff;padding:20px 24px}}
 main{{max-width:760px;margin:24px auto;padding:0 16px}}
 .g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
 .c{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8}}
 .c b{{display:block;font-size:26px}} .c span{{color:#666;font-size:13px}}
 section{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8;margin-top:16px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px;border-bottom:1px solid #eee}}
 small{{color:#666}}
</style></head><body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">AI guide results - last {s['days']} days</small></header>
<main>
<div class="g">{cards}</div>
<section><b>Daily activity</b> <small>grey = conversations, colour = leads</small>
<svg viewBox="0 0 600 115" width="100%" role="img" aria-label="Daily conversations and leads">{''.join(bars)}</svg></section>
<section><b>Recent leads</b><table><tr><th>Date</th><th>Who</th><th>What they wanted</th><th>Via</th><th>Status</th></tr>{rows or '<tr><td colspan=5>No leads yet.</td></tr>'}</table></section>
<p><small>Estimated pipeline = leads x the average lead value agreed with your provider. Contact details are not shown on this page.</small></p>
</main></body></html>"""
    return HTMLResponse(page)


# -------------------------------------------------------------------- admin
admin = [Depends(require_admin)]


@app.get("/admin-ui")
async def admin_ui():
    """Static dashboard shell. It holds no data; the page asks for the admin token and calls /admin/*."""
    return FileResponse(STATIC_DIR / "admin.html", media_type="text/html", headers={"Cache-Control": "no-store"})


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
    voice_daily_limit: int | None = Field(default=None, ge=0, le=100_000)
    booking_url: str | None = None
    lead_webhook_url: str | None = None
    incentive: str | None = None
    timezone: str | None = None
    business_hours: dict[str, list[list[str]]] | None = None
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    min_notice_hours: int | None = Field(default=None, ge=0, le=720)
    max_days_ahead: int | None = Field(default=None, ge=1, le=365)
    native_booking: bool | None = None
    notify_email: str | None = None
    sms_enabled: bool | None = None
    sms_from: str | None = None
    lead_sms_template: str | None = None
    review_url: str | None = None
    lead_value_cents: int | None = Field(default=None, ge=0, le=100_000_000)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value):
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError("unknown IANA timezone, e.g. America/Chicago")
        return value

    @field_validator("lead_sms_template")
    @classmethod
    def _template(cls, value):
        if value is None:
            return value
        try:
            value.format(first="A", name="A", business="A")
        except Exception:
            raise ValueError("template may only use {first}, {name} and {business}")
        return value

    @field_validator("business_hours")
    @classmethod
    def _hours(cls, value):
        if value is None:
            return value
        for key, windows in value.items():
            if key not in DAYS:
                raise ValueError(f"unknown day '{key}' (use {', '.join(DAYS)})")
            for window in windows:
                if len(window) != 2 or not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", w) for w in window):
                    raise ValueError("each window must be [\"HH:MM\", \"HH:MM\"]")
                if window[0] >= window[1]:
                    raise ValueError("a window must open before it closes")
        return value


class CloneRequest(BaseModel):
    name: str
    site_url: str | None = None
    slug: str | None = None


class LeadUpdate(BaseModel):
    status: Literal["new", "contacted", "booked", "won", "lost"] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    value_cents: int | None = Field(default=None, ge=0, le=100_000_000)


class AppointmentUpdate(BaseModel):
    status: Literal["booked", "completed", "cancelled", "no_show"]


def _with_snippet(tenant: dict) -> dict:
    base = settings.public_base_url
    return {
        **tenant,
        "embed_snippet": f'<script src="{base}/widget.js" data-key="{tenant["public_key"]}" defer></script>',
        "demo_url": f"{base}/demo/{tenant['slug']}?presenter=1",
        "report_url": f"{base}/report/{tenant['report_token']}",
        "sms_webhook_url": f"{base}/api/v1/sms/{tenant['public_key']}",
    }


async def _require_tenant(slug: str) -> dict:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


@app.post("/admin/tenants", dependencies=admin)
async def admin_create_tenant(body: TenantCreate):
    data = body.model_dump()
    tenant = await tenants.create(data.pop("name"), data.pop("site_url"), slug=data.pop("slug"), **data)
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


@app.post("/admin/tenants/{slug}/clone", dependencies=admin)
async def admin_clone_tenant(slug: str, body: CloneRequest):
    """Snapshot: copy settings (persona, hours, SMS template...) to a new client. No knowledge or contacts."""
    source = await _require_tenant(slug)
    return _with_snippet(await tenants.clone(source, body.name, body.site_url, body.slug))


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
        tenant["id"], min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.patch("/admin/leads/{lead_id}", dependencies=admin)
async def admin_update_lead(lead_id: str, body: LeadUpdate):
    data = body.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    parts = [f"{col} = ${i}" for i, col in enumerate(data, start=2)]
    try:
        row = await db.pool().fetchrow(
            f"UPDATE leads SET {', '.join(parts)}, updated_at = now() WHERE id = $1::uuid RETURNING *",
            lead_id, *data.values(),
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown lead")
    return dict(row)


@app.get("/admin/tenants/{slug}/appointments", dependencies=admin)
async def admin_appointments(slug: str, status: str | None = None, limit: int = 100):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM appointments WHERE tenant_id = $1 AND ($2::text IS NULL OR status = $2) "
        "ORDER BY starts_at DESC LIMIT $3",
        tenant["id"], status, min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.patch("/admin/appointments/{appointment_id}", dependencies=admin)
async def admin_update_appointment(appointment_id: str, body: AppointmentUpdate):
    try:
        row = await db.pool().fetchrow(
            "UPDATE appointments SET status = $2 WHERE id = $1::uuid RETURNING *", appointment_id, body.status
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment id")
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown appointment")
    appt = dict(row)
    tenant = await tenants.get_by_id(appt["tenant_id"])
    await automation.on_appointment_status(tenant, appt, body.status)
    return appt


@app.get("/admin/tenants/{slug}/outbox", dependencies=admin)
async def admin_outbox(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT id, kind, channel, to_addr, status, attempts, last_error, send_at, sent_at "
        "FROM outbox WHERE tenant_id = $1 ORDER BY id DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.get("/admin/tenants/{slug}/conversations", dependencies=admin)
async def admin_conversations(slug: str, limit: int = 50):
    """Recent conversations with their transcripts - review these monthly to improve the knowledge base."""
    tenant = await _require_tenant(slug)
    convs = await db.pool().fetch(
        "SELECT * FROM conversations WHERE tenant_id = $1 AND channel <> 'eval' ORDER BY started_at DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 200),
    )
    out = []
    for conv in convs:
        msgs = await db.pool().fetch(
            "SELECT role, content, flag, created_at FROM messages WHERE conversation_id = $1 ORDER BY id",
            conv["id"],
        )
        out.append({**dict(conv), "messages": [dict(m) for m in msgs]})
    return out


@app.get("/admin/tenants/{slug}/stats", dependencies=admin)
async def admin_stats(slug: str, days: int = 30):
    return await _stats(await _require_tenant(slug), days)
